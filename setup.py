from setuptools import setup

description = '''\
Library derived from https://github.com/SoCo/socos,
but heavily modified to use asyncio and aiohttp.
'''

install_requires = [
    'aiohttp',                  # not sure of minimum version
    'python-didl-lite >= 1.2.6',
]
dev_requires = [
    'pyflakes',
    'pycodestyle',
    'mypy',
    'pytest >= 6.0.0',
]

setup(
    name='aiosonos',
    version='0.0',
    short_description='asyncio library for Sonos players',
    description=description,
    author='Greg Ward',
    author_email='greg@gerg.ca',
    packages=['aiosonos'],
    install_requires=install_requires,
    extras_require={'dev': dev_requires},
)
