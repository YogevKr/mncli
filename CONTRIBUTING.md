# Contributing

## Development Setup

Run the test suite with the standard library:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_mncli.py
```

Check the package build:

```sh
uv build --clear
```

Install a live editable copy:

```sh
uv tool install --editable .
```

## Pull Requests

Keep changes focused and include a regression test for behavior changes. Before
opening a pull request, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_mncli.py
uv build --clear
```
