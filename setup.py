from setuptools import setup

description = '''\
Library derived from https://github.com/SoCo/socos,
but heavily modified to use asyncio and aiohttp.
'''

install_requires = [
    'aiohttp',                  # not sure of minimum version
    'python-didl-lite >= 1.2.6',
]
cli_requires = [
    'click >= 8.1',
]
dev_requires = [
    'pyflakes',
    'pycodestyle',
    'mypy',
    'pytest >= 6.0.0',
    'pytest-asyncio <= 0.17.0',    # 0.17.0 requires Python >= 3.7
    'types-click',
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
    extras_require={
        'cli': cli_requires,
        'dev': dev_requires,
    },
    entry_points={
        'console_scripts': [
            'sntool = aiosonos.sntool:main',
        ],
    },
)
