from setuptools import setup

description = '''\
Library derived from https://github.com/SoCo/socos,
but heavily modified to use asyncio and aiohttp.
'''

setup(
    name='aiosonos',
    version='0.0',
    short_description='asyncio library for Sonos players',
    description=description,
    author='Greg Ward',
    author_email='greg@gerg.ca',
    packages=['aiosonos'],
)
