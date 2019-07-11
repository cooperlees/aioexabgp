# aioexabgp

An example asyncio non blocking ExaBGP Library

- This does not implement BGP in any way, but only talks to exabgp's [API](https://github.com/Exa-Networks/exabgp/wiki/Controlling-ExaBGP-:-interacting-from-the-API)

## Client

Library to perform X asynchronous healthchecks (of an IGP or a `ping` check)
and handle announcing + withdrawing routes

Goals:

- Allow multiple health checks to run and any fails cause routes to be withdrawn
- All healthchecks to be non blocking via asyncio

### Use

Get an instance of ExaBGPClient and add healthchecks to
influence the addition and withdrawal of advertised routes.

#### Sample

- *TODO:* Please refer to `sample_exa_injector.py` to see how we propose usage of the client library

### Design

- `__intit__.py`: Base ExaBGPClient for you to use and extend
- `healthchecks.py`: Base and ping exabgp examples

## Library

Will be adding asyncio helpers for working with exabgp

### Modules

- `pipes.py`: Class to hold ownership of the named pipes and optional synconization lock

## Running CI / Testing

We are all `ptr` powered. To run CI:

- https://github.com/facebookincubator/ptr/

```shell
cd .  # This dir
python3 -m venv /tmp/test_aioexabgp
/tmp/test_aioexabgp/bin/pip install --upgrade pip setuptool ptr

# For first run state we want to `keep` the venv via -k
/tmp/test_aio/bin/ptr -k

# Subsiquent Runs (venv creation is slow)
/tmp/test_aio/bin/ptr --venv PATH_PTR_PRINTED_OUT
```

- **More Information:** ptr [README.md](https://github.com/facebookincubator/ptr/blob/master/README.md)

### Run tests only

You can also run unittests only via

- `python3 setup.py test`

to debug a specific test easily rather than running the full suite
