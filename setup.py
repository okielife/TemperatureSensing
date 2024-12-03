from setuptools import setup

from sensing.copier import Copier


setup(
    name='sensing',
    version='0.1',
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
