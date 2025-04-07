from os import environ
from sys import modules
from time import localtime, struct_time
from types import ModuleType
from unittest import TestCase
from unittest.mock import MagicMock, patch

mock_time = ModuleType('time')
mock_time.sleep = MagicMock('sleep')
mock_time.localtime = lambda x: localtime(x)
modules['time'] = mock_time

# Create a few fake modules and add them to sys.modules
fake_led = MagicMock(name="fake_led")

fake_rtc = ModuleType("rtc")
fake_rtc.RTC = MagicMock()
fake_rtc.RTC.datetime = MagicMock()
modules["rtc"] = fake_rtc

fake_wifi = ModuleType("wifi")
fake_wifi.radio = MagicMock(name="radio")
modules["wifi"] = fake_wifi

fake_dio = ModuleType("digitalio")
fake_dio.DigitalInOut = MagicMock(name="DigitalInOut")
fake_pin = MagicMock()
fake_pin.switch_to_output = MagicMock()
fake_dio.DigitalInOut.return_value = fake_pin
modules["digitalio"] = fake_dio

mock_board = ModuleType('board_definitions')
mock_board.raspberry_pi_pico_w = MagicMock('raspberry_pi_pico_w')
mock_board.raspberry_pi_pico_w.GP4 = fake_pin
mock_board.raspberry_pi_pico_w.GP12 = fake_pin
modules['board_definitions'] = mock_board


class FakeSocket:
    def __init__(self, *_):
        self.settimeout = lambda _x: None
        self.sendto = lambda _x, _y: None

    # noinspection PyMethodMayBeStatic
    def recv_into(self, x):
        x[:] = b'\x1c\x02\x03\xe8\x00\x00\x02Z\x00\x00\n\xf4\xc7f.F\xeb\x9e\x85\x85\x01s;m\x00\x00\x00\x00\x00\x00\x00\x00\xeb\x9e\x8cd\xa7z\xf7\r\xeb\x9e\x8cd\xa7\x82w\xf6'  # noqa: E501

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class FakeSocketPool:
    AF_INET = None
    SOCK_DGRAM = None

    def __init__(self, *_):
        self.getaddrinfo = lambda _x, _y: [[0, 0, 0, 0, 0]]
        self.socket = lambda _x, _y: FakeSocket()


fake_conn_manager = ModuleType("adafruit_connection_manager")
fake_conn_manager.get_radio_socketpool = MagicMock(return_value=FakeSocketPool())
fake_conn_manager.get_radio_ssl_context = MagicMock(return_value=MagicMock())
modules["adafruit_connection_manager"] = fake_conn_manager

fake_ds18x20 = ModuleType("adafruit_ds18x20")
fake_sensor = MagicMock(temperature=20)
fake_ds18x20.DS18X20 = MagicMock(return_value=fake_sensor)
modules["adafruit_ds18x20"] = fake_ds18x20

fake_bus = MagicMock()
fake_bus.scan = MagicMock()
fake_one_wire = ModuleType("adafruit_onewire.bus")
fake_one_wire.OneWireBus = MagicMock(return_value=fake_bus)
modules["adafruit_onewire.bus"] = fake_one_wire

fake_requests = ModuleType("adafruit_requests")
fake_session_instance = MagicMock()
fake_session_instance.get = MagicMock(name="get")
fake_put_response = MagicMock()
fake_put_response.status_code = 200
fake_session_instance.put = MagicMock(name="put")
fake_session_instance.put.return_value = fake_put_response
fake_requests.Session = MagicMock(return_value=fake_session_instance)
modules["adafruit_requests"] = fake_requests

# and only after that do we import the Sensor class
from sensing.sensing import Sensor  # noqa: E402


class TestSensorNew(TestCase):

    @staticmethod
    def _init_clock():
        s = Sensor(fake_led)
        c = fake_rtc.RTC()
        socket_pool, session = Sensor.init_connection_variables()
        s.set_clock_to_cst(socket_pool, c)
        return c

    def test_init_connection_variables(self):
        """Check to make sure the function returns pool, session types as returned by the library"""
        socket_pool, session = Sensor.init_connection_variables()
        self.assertIsInstance(socket_pool, FakeSocketPool)
        self.assertIsInstance(session, type(fake_session_instance))

    @patch('builtins.print')
    def test_connect_to_wifi(self, _mock_print):
        # first check if Wi-Fi is already set
        fake_wifi.radio.ipv4_address = "1.1.1.1"
        s = Sensor(fake_led)
        s.connect_to_wifi()  # if we made it here, it's fine
        # now let's disable the ip address and see what happens
        fake_wifi.radio.ipv4_address = None
        # first what if we don't have a Wi-Fi environment variable
        if 'WIFI' in environ:  # pragma: no cover
            del environ['WIFI']
        with self.assertRaises(RuntimeError):
            s.connect_to_wifi()
        # second what if we DO have a Wi-Fi variable with one entry
        with patch.dict(environ, {"WIFI": "x,y,z"}):
            s.connect_to_wifi()
        # now if we have two Wi-Fi entries, and the first one fails
        fake_wifi.radio.connect.side_effect = [ConnectionError, None]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            s.connect_to_wifi()
        fake_wifi.radio.connect.side_effect = None
        # and of course, if the first one passes, it should just take it
        fake_wifi.radio.connect.side_effect = [None, ConnectionError]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            s.connect_to_wifi()
        fake_wifi.radio.connect.side_effect = None
        # and if we get connection errors the entire first pass, we should try again
        fake_wifi.radio.connect.side_effect = [ConnectionError, ConnectionError, None]
        with patch.dict(environ, {"WIFI": "x,y,z;1,2,3"}):
            s.connect_to_wifi()
        fake_wifi.radio.connect.side_effect = None

    def test_github_token(self):
        # first what happens if we forgot to set the TOKENS_URL environment variable
        if 'TOKEN_URL' in environ:  # pragma: no cover
            del environ['TOKEN_URL']
        with self.assertRaises(RuntimeError):
            Sensor.github_token(fake_session_instance)
        # ok, now if we do have one let's make sure it handles bad response
        fake_session_instance.get.side_effect = ConnectionError
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            with self.assertRaises(Exception):
                # could be HTTPError, ConnectionError, etc., so just catch Exception
                Sensor.github_token(fake_session_instance)
        fake_session_instance.get.side_effect = None
        fake_response = MagicMock(name="response")
        fake_response.content = b"1\n2\n3\n4"
        fake_session_instance.get.return_value = fake_response
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            gh_token = Sensor.github_token(fake_session_instance)
        self.assertEqual("4321", gh_token)

    def test_set_extra_hot_ports(self):
        # first be OK if we don't have any defined
        if 'EXTRA_HOTS' in environ:  # pragma: no cover
            del environ['EXTRA_HOTS']
        Sensor.set_extra_hot_ports()  # should just pass and leave
        # now what if we do have some, but there's a bad one
        with patch.dict(environ, {"EXTRA_HOTS": "x,y,z"}):
            with self.assertRaises(AttributeError):
                Sensor.set_extra_hot_ports()
        # ok, now some valid ones for the Pico
        with patch.dict(environ, {"EXTRA_HOTS": "GP4,GP12"}):
            Sensor.set_extra_hot_ports()

    @patch('builtins.print')
    def test_set_clock_to_cst(self, _mock_print):
        s = Sensor(fake_led)
        c = fake_rtc.RTC()
        socket_pool, session = Sensor.init_connection_variables()
        s.set_clock_to_cst(socket_pool, c)
        self.assertIsInstance(c.datetime, struct_time)

    @patch('builtins.print')
    def test_get_gpio_port_instance(self, _mock_print):
        s = Sensor(fake_led)
        c = self._init_clock()
        # first call with a good pin name (as defined in the mock above)
        p = s.get_gpio_port_instance(c, 'GP4')
        self.assertIsInstance(p, type(fake_pin))
        # then call with a bad pin name
        with self.assertRaises(AttributeError):
            s.get_gpio_port_instance(c, 'ABC')

    @patch('builtins.print')
    def test_get_all_sensors_from_env(self, _mock_print):
        s = Sensor(fake_led)
        c = self._init_clock()
        # first what if we don't have any defined
        if 'SENSORS' in environ:  # pragma: no cover
            del environ['SENSORS']
        with self.assertRaises(RuntimeError):
            s.get_all_sensors_from_env(c)
        # now what if we do have some sensors, but there's a bad port specification
        fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP13"}):
            with self.assertRaises(AttributeError):
                s.get_all_sensors_from_env(c)
        # next what if we specify sensors correctly, but the init fails (bad wiring connection)
        fake_bus.scan.return_value = []
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            with self.assertRaises(RuntimeError):
                s.get_all_sensors_from_env(c)
        # finally what if we're all good
        fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP12"}):
            sensors = s.get_all_sensors_from_env(c)
            self.assertEqual(2, len(sensors))
            for i, s in sensors.items():
                self.assertIsInstance(i, str)
                self.assertIsInstance(s, type(fake_sensor))

    @patch('builtins.print')
    def test_warm_up_temperature_sensors(self, _mock_print):
        s = Sensor(fake_led)
        c = self._init_clock()
        fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4;Name2,GP12"}):
            sensors = s.get_all_sensors_from_env(c)
        s.warm_up_temperature_sensors(sensors, c)

    @patch('builtins.print')
    def test_report_single_sensor(self, _mock_print):
        s = Sensor(fake_led)
        c = self._init_clock()
        fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            sensors = s.get_all_sensors_from_env(c)
            single_sensor_id = next(iter(sensors.keys()))
        socket_pool, session = Sensor.init_connection_variables()
        fake_session_instance.put.side_effect = ConnectionError
        b = s.report_single_sensor(c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertFalse(b)  # just returns False, doesn't abort
        fake_session_instance.put.side_effect = None
        fake_put_response.status_code = 404
        b = s.report_single_sensor(c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertFalse(b)  # just returns False, doesn't abort
        fake_put_response.status_code = 200
        b = s.report_single_sensor(c, session, single_sensor_id, sensors[single_sensor_id], 'token')
        self.assertTrue(b)  # just returns False, doesn't abort

    @patch('builtins.print')
    def test_report_all_sensors(self, _mock_print):
        s = Sensor(fake_led)
        c = self._init_clock()
        fake_bus.scan.return_value = [0]
        with patch.dict(environ, {"SENSORS": "Name1,GP4"}):
            sensors = s.get_all_sensors_from_env(c)
        socket_pool, session = Sensor.init_connection_variables()
        fake_session_instance.put.side_effect = ConnectionError
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            b = s.report_all_sensors(session, c, sensors)
        self.assertFalse(b)  # just returns False, doesn't abort
        fake_session_instance.put.side_effect = None
        fake_put_response.status_code = 200
        with patch.dict(environ, {"TOKEN_URL": "dummy"}):
            b = s.report_all_sensors(session, c, sensors)
        self.assertTrue(b)  # just returns False, doesn't abort

    @patch('builtins.print')
    def test_run_once(self, _mock_print):
        s = Sensor(fake_led)
        fake_bus.scan.return_value = [0]
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            s.run_once()
        self.assertTrue(s.success)

        s = Sensor(fake_led)
        fake_bus.scan.return_value = []
        with patch.dict(environ,
                        {"SENSORS": "Name1,GP4", "TOKEN_URL": "dummy", "EXTRA_HOTS": "GP4,GP12", "WIFI": "x,y,z"}):
            s.run_once()
        self.assertFalse(s.success)
