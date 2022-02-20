# aiosonos: asyncio-based Sonos client library for  Python

aiosonos is a Python client library for Sonos products
based on asyncio and aiohttp.
It is derived from
[SoCo](https://github.com/SoCo/SoCo),
but structured very differently.

Right now, aiosonos is pre-release and barely functional.
Here are reasons you should stick with SoCo
instead of using aiosonos:

  * SoCo is more mature
  * SoCo has been more widely tested
  * SoCo has many more features

And here are reasons you might want to try aiosonos:

  * aiosonos uses asyncio,
    so is potentially useful
    if you want Sonos support
    in an asyncio-based application
  * aiosonos is much smaller and simpler,
    so the code is easier to understand (IMHO)
  * aiosonos is more cleanly structured (IMHO)
  * aiosonos never does network I/O
    unless you explicitly ask for it

## Usage

For now, the documentation is the source code.
Start in aiosonos/api.py and aiosonos/discover.py.
Everything else is an implementation detail.

## Development

Setup a virtualenv:
```
python3 -m venv venv
source venv/bin/activate
pip install -e '.[dev]'
```

Run the tests:
```
./test.sh
```
