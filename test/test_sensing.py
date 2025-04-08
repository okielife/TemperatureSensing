from os import environ
from sys import modules
from time import localtime, struct_time, strftime
from types import ModuleType
from unittest import TestCase
from unittest.mock import MagicMock, patch


class TestSensor(TestCase):
    sensor_class: type

    # *** Here are a few convenience classes that minimally mock the actual implementation
    class FakeSocket:
        def __init__(self, *_):
            self.settimeout = lambda _x: None
            self.sendto = lambda _x, _y: None

        # noinspection PyMethodMayBeStatic
        def recv_into(self, x):
            x[:] = (
                b'\x1c\x02\x03\xe8\x00\x00\x02Z\x00\x00\n\xf4\xc7f.F\xeb\x9e\x85\x85\x01s;m\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\xeb\x9e\x8cd\xa7z\xf7\r\xeb\x9e\x8cd\xa7\x82w\xf6'
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            pass

    class FakeSocketPool:
        AF_INET = None
        SOCK_DGRAM = None

        def __init__(self, *_):
            self.getaddrinfo = lambda _x, _y: [[0, 0, 0, 0, 0]]
            self.socket = lambda _x, _y: TestSensor.FakeSocket()

    class FakePin:
        def switch_to_output(self, value): pass

    @classmethod
    def setUpClass(cls):
        """
        In this class method, we set up the types and mock module imports before importing the Sensor class to ensure
        our mocked versions are used.  Instances which are needed by actual unit test methods are stored on the class.

        :return: None
        """
        mock_time = ModuleType('time')
        mock_time.sleep = MagicMock('sleep')
        mock_time.localtime = lambda x: localtime(x)
        mock_time.struct_time = struct_time
        mock_time.strftime = strftime
        modules['time'] = mock_time

        cls.fake_rtc = ModuleType("rtc")
        cls.fake_rtc.RTC = MagicMock()
        cls.fake_rtc.RTC.datetime = MagicMock()
        modules["rtc"] = cls.fake_rtc

        cls.fake_wifi = ModuleType("wifi")
        cls.fake_wifi.radio = MagicMock(name="radio")
        modules["wifi"] = cls.fake_wifi

        fake_dio = ModuleType("digitalio")
        fake_dio.DigitalInOut = MagicMock(return_value = TestSensor.FakePin())
        fake_dio.Direction = MagicMock()
        modules["digitalio"] = fake_dio

        mock_board = ModuleType('board_definitions')
        mock_board.raspberry_pi_pico_w = MagicMock('raspberry_pi_pico_w')
        mock_board.raspberry_pi_pico_w.GP4 = TestSensor.FakePin()
        mock_board.raspberry_pi_pico_w.GP12 = TestSensor.FakePin()
        mock_board.raspberry_pi_pico_w.LED = TestSensor.FakePin()
        modules['board_definitions'] = mock_board

        cls.fake_controller = ModuleType('microcontroller')
        cls.fake_controller.reset = MagicMock(return_value=True)
        cls.fake_controller.Pin = MagicMock(return_value=TestSensor.FakePin())
        modules['microcontroller'] = cls.fake_controller

        fake_conn_manager = ModuleType("adafruit_connection_manager")
        fake_conn_manager.get_radio_socketpool = MagicMock(return_value=TestSensor.FakeSocketPool())
        fake_conn_manager.get_radio_ssl_context = MagicMock(return_value=MagicMock())
        modules["adafruit_connection_manager"] = fake_conn_manager

        fake_ds18x20 = ModuleType("adafruit_ds18x20")
        cls.fake_sensor = MagicMock(temperature=20)
        fake_ds18x20.DS18X20 = MagicMock(return_value=cls.fake_sensor)
        modules["adafruit_ds18x20"] = fake_ds18x20

        cls.fake_bus = MagicMock()
        cls.fake_bus.scan = MagicMock()
        fake_one_wire = ModuleType("adafruit_onewire.bus")
        fake_one_wire.OneWireBus = MagicMock(return_value=cls.fake_bus)
        modules["adafruit_onewire.bus"] = fake_one_wire

        fake_requests = ModuleType("adafruit_requests")
        cls.fake_session_instance = MagicMock()
        cls.fake_session_instance.get = MagicMock(name="get")
        cls.fake_put_response = MagicMock()
        cls.fake_put_response.status_code = 200
        cls.fake_session_instance.put = MagicMock(name="put")
        cls.fake_session_instance.put.return_value = cls.fake_put_response
        fake_requests.Session = MagicMock(return_value=cls.fake_session_instance)
        modules["adafruit_requests"] = fake_requests

        # and only after that do we import the Sensor class
        from sensing import Sensor  # noqa: E402
        cls.sensor_class = Sensor

    def setUp(self):
        self.s = self.sensor_class()
        # clear out any environment variables, but store the values so we can reset them in tearDown
        self.responsive_environment_variables = ['WIFI', 'TOKEN_URL', 'EXTRA_HOTS', 'SENSORS']
        self.env_values = []
        for r in self.responsive_environment_variables:
            if r in environ:  # pragma: no cover
                self.env_values.append(environ[r])
                del environ[r]
            else:
                self.env_values.append(None)
        self.c = self.get_clock()

    def tearDown(self):
        for name, value in zip(self.responsive_environment_variables, self.env_values):
            if value:  # pragma: no cover
                environ[name] = value

    def get_clock(self):
        c = self.fake_rtc.RTC()
        with patch('builtins.print') as _:
            socket_pool, session = self.s.init_connection_variables()
            self.s.set_clock_to_cst(socket_pool, c)
        return c

    def test_init_connection_variables(self):
        """Check to make sure the function returns pool, session types as returned by the library"""
        socket_pool, session = self.s.init_connection_variables()
        self.assertIsInstance(socket_pool, TestSensor.FakeSocketPool)
        self.assertIsInstance(session, type(self.fake_session_instance))

    @patch('builtins.print')
    def test_connect_to_wifi(self, _mock_print):
        # first check if Wi-Fi is already set
        self.fake_wifi.radio.ipv4_address = "1.1.1.1"
        self.s.connect_to_wifi()  # if we made it here, it's fine
        # now let's disable the ip address and see what happens
        self.fake_wifi.radio.ipv4_address = None
        # first what if we don't have a Wi-Fi environment variable
        with self.assertRaises(RuntimeError):
            self.s.connect_to_wifi()
        # second what if we DO have a Wi-Fi variable with one entry
        with patch.dict(environ, {"WIFI": "x,y,z"}):
            self.s.connect_to_wifi()
        # now if we have two Wi-Fi entries, and the first one fails
        self.fake_wifi.radio.connect.side_effect = [ConnectionError, None]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            self.s.connect_to_wifi()
        self.fake_wifi.radio.connect.side_effect = None
        # and of course, if the first one passes, it should just take it
        self.fake_wifi.radio.connect.side_effect = [None, ConnectionError]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            self.s.connect_to_wifi()
        self.fake_wifi.radio.connect.side_effect = None
        # and if we get connection errors the entire first pass, we should try again
        self.fake_wifi.radio.connect.side_effect = [ConnectionError, ConnectionError, None]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            self.s.connect_to_wifi()
        self.fake_wifi.radio.connect.side_effect = None

    def test_github_token(self):
        # first what happens if we forgot to set the TOKENS_URL environment variable
        with self.assertRaises(RuntimeError):
            self.s.github_token(self.fake_session_instance)
        # ok, now if we do have one let's make sure it handles bad response
        self.fake_session_instance.get.side_effect = ConnectionError
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            with self.assertRaises(Exception):
                # could be HTTPError, ConnectionError, etc., so just catch Exception
                self.s.github_token(self.fake_session_instance)
        self.fake_session_instance.get.side_effect = None
        fake_response = MagicMock(name="response")
        fake_response.content = b"1\n2\n3\n4"
        self.fake_session_instance.get.return_value = fake_response
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            gh_token = self.s.github_token(self.fake_session_instance)
        self.assertEqual("4321", gh_token)

    def test_set_extra_hot_ports(self):
        # first be OK if we don't have any defined
        self.s.set_extra_hot_ports()  # should just pass and leave
        # now what if we do have some, but there's a bad one
        with patch.dict(environ, {"EXTRA_HOTS": "x,y,z"}):
            with self.assertRaises(AttributeError):
                self.s.set_extra_hot_ports()
        # ok, now some valid ones for the Pico
        with patch.dict(environ, {"EXTRA_HOTS": "GP4,GP12"}):
            self.s.set_extra_hot_ports()

    @patch('builtins.print')
    def test_set_clock_to_cst(self, _mock_print):
        c = self.fake_rtc.RTC()
        socket_pool, session = self.s.init_connection_variables()
        self.s.set_clock_to_cst(socket_pool, c)
        self.assertIsInstance(c.datetime, struct_time)

    @patch('builtins.print')
    def test_get_gpio_port_instance(self, _mock_print):
        # first call with a good pin name (as defined in the mock above)
        p = self.s.get_gpio_port_instance(self.c, 'GP4')
        self.assertIsInstance(p, TestSensor.FakePin)
        # then call with a bad pin name
        with self.assertRaises(RuntimeError):
            self.s.get_gpio_port_instance(self.c, 'ABC')

    @patch('builtins.print')
    def test_get_all_sensors_from_env(self, _mock_print):
        # first what if we don't have any defined
        with self.assertRaises(RuntimeError):
            self.s.get_all_sensors_from_env(self.c)
        # now what if we do have some sensors, but there's a bad port specification
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP13"}):
            with self.assertRaises(RuntimeError):
                self.s.get_all_sensors_from_env(self.c)
        # next what if we specify sensors correctly, but the init fails (bad wiring connection)
        self.fake_bus.scan.return_value = []
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            with self.assertRaises(RuntimeError):
                self.s.get_all_sensors_from_env(self.c)
        # finally what if we're all good
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP12"}):
            sensors = self.s.get_all_sensors_from_env(self.c)
            self.assertEqual(2, len(sensors))
            for i, s in sensors.items():
                self.assertIsInstance(i, str)
                self.assertIsInstance(s, type(self.fake_sensor))

    @patch('builtins.print')
    def test_warm_up_temperature_sensors(self, _mock_print):
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP12"}):
            sensors = self.s.get_all_sensors_from_env(self.c)
        self.s.warm_up_temperature_sensors(sensors, self.c)

    @patch('builtins.print')
    def test_report_single_sensor(self, _mock_print):
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            sensors = self.s.get_all_sensors_from_env(self.c)
            single_sensor_id = next(iter(sensors.keys()))
        socket_pool, session = self.s.init_connection_variables()
        self.fake_session_instance.put.side_effect = ConnectionError
        b = self.s.report_single_sensor(self.c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertFalse(b)  # just returns False, doesn't abort
        self.fake_session_instance.put.side_effect = None
        self.fake_put_response.status_code = 404
        b = self.s.report_single_sensor(self.c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertFalse(b)  # just returns False, doesn't abort
        self.fake_put_response.status_code = 200
        b = self.s.report_single_sensor(self.c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertTrue(b)  # just returns False, doesn't abort

    @patch('builtins.print')
    def test_report_all_sensors(self, _mock_print):
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            sensors = self.s.get_all_sensors_from_env(self.c)
        socket_pool, session = self.s.init_connection_variables()
        self.fake_session_instance.put.side_effect = ConnectionError
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            with self.assertRaises(RuntimeError):
                self.s.report_all_sensors(session, self.c, sensors)
        self.fake_session_instance.put.side_effect = None
        self.fake_put_response.status_code = 200
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            self.s.report_all_sensors(session, self.c, sensors)

    @patch('builtins.print')
    def test_run_once(self, _mock_print):
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            self.s.run_once()
        self.assertTrue(self.s.success)
        s2 = self.sensor_class()
        self.fake_bus.scan.return_value = []
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            s2.run_once()
        self.assertFalse(s2.success)

    @patch('builtins.print')
    def test_pico_main(self, _mock_print):
        self.fake_controller.reset.reset_mock()
        self.fake_bus.scan.return_value = [0]
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            self.s.run_loop()
        self.assertTrue(self.s.success)
        self.fake_controller.reset.assert_called_once()
        self.fake_controller.reset.reset_mock()
        s2 = self.sensor_class()
        self.fake_bus.scan.return_value = []
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            s2.run_loop()
        self.assertFalse(s2.success)
        self.fake_controller.reset.assert_called_once()
