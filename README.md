# aioexabgp

An example asyncio non blocking ExaBGP Library

- This does not implement BGP in any way, but only talks to exabgp's [API](https://github.com/Exa-Networks/exabgp/wiki/Controlling-ExaBGP-:-interacting-from-the-API)

## Client

Library to perform X asynchronous healthchecks (e.g query an IGP or a `ping` check)
and handle announcing + withdrawing routes. The library will also be able
to read routes from ExaBGP peers and then program any FIB you write a Handler for
(e.g. Linux Route table or an IGP)

Goals:

- Allow multiple health checks to run and any fails cause routes to be withdrawn
- All healthchecks to be non blocking via asyncio

### Use

Get an instance of `Announcer` class and add healthchecks to
influence the addition and withdrawal of advertised routes.

#### Sample

The sample exists to show how you could extend the Announcer for route add and withdrawal
via printing ExaBGP commands to STDOUT.

- Please refer to `aioexabgp.announcer.Announcer` for referenced class
- `sample_announcer.json` is the configuration that drives `sample.py`

`aioexabgp.announcer.sample` has a runnable example. `-D` here is important for dry run. This is a bad example that needs sudo to `/sbin/ip`.
Steps to use:

- Create a venv
- cd to this repo base
- Install aioexabgp
- Run

```shell
python3 -m venv /tmp/tae
cd .
/tmp/tae/bin/pip install --upgrade pip setuptools
/tmp/tae/bin/pip install [-e] .
# Run the code
/tmp/tae/bin/python aioexabgp/announcer/sample.py -c aioexabgp/announcer/sample_announcer.json -D -d
```

You can also add some IPs to loopback to see health checks pass and fail
**MacOS X**

- Add: `sudo ifconfig lo0 inet6 alias 69::69`
- Remove: `sudo ifconfig lo0 inet6 -alias 69::69`

### Modules

- `exabgpparser.py`: All the API JSON parsing into **FibPrefix** named tuples
- `pipes.py`: Class to hold ownership of the named pipes and optional synconization lock

## Running CI / Unit Tests

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
