from setuptools import setup

from sensing.copier import Copier

# TODO: Rework the mock classes for socket pools so that it is easier to test the CST calc function
# TODO: Get unit test coverage for code.py
# TODO: Get unit test coverage for copier.py
# TODO: Consider what to do with the sensing/ folder, hopefully just get rid of it I think
# TODO: Maybe get everything inside code.py completely
# TODO: Once this list is complete, tag this repo as 1.0
setup(
    name='sensing',
    version='0.8',
    packages=['sensing'],
    url='github.com/okielife/TempSensors',
    license='',
    author='Edwin Lee',
    author_email='',
    description='',
    cmdclass={
        'copy': Copier,
    },
)
