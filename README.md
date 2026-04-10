# mncli

Lightweight CLI for interacting with a running marimo notebook.

`mncli` is a thin wrapper over the marimo kernel HTTP API. It gives agents and
scripts stable verbs for starting a notebook, inspecting cells, editing cells,
running cells, installing kernel packages, and executing scratch code.

## Requirements

- Python 3.10+
- `uv` for recommended installation
- marimo, either available in the target project or via `uvx`
- `curl` and `jq`, used by the bundled HTTP transport

By default, `mncli` uses the bundled `mncli-execute-code` transport installed
beside the CLI. Override the transport path with:

```sh
export MNCLI_EXECUTE_SCRIPT=/path/to/transport-script
```

## Install

From this checkout:

```sh
uv tool install .
```

For live local development:

```sh
uv tool install --editable .
```

Make sure uv's tool bin directory is on `PATH`:

```sh
uv tool dir --bin
```

From GitHub:

```sh
uv tool install git+https://github.com/YogevKr/mncli.git
```

## Usage

Start a notebook server:

```sh
mncli servers
mncli start analysis.py --headless --port 2718
```

For pixi-managed projects:

```sh
mncli start analysis.py --runner pixi
```

Use the running notebook:

```sh
mncli --port 2718 status
mncli --port 2718 exec --code 'print("hello")'
mncli notes
```

Print the version:

```sh
mncli --version
```

## Development

Run tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_mncli.py
```

Build the package:

```sh
uv build --clear
```

Install into an isolated tool dir for verification:

```sh
rm -rf /tmp/mncli-uv-tools /tmp/mncli-uv-bin
mkdir -p /tmp/mncli-uv-tools /tmp/mncli-uv-bin
UV_TOOL_DIR=/tmp/mncli-uv-tools UV_TOOL_BIN_DIR=/tmp/mncli-uv-bin uv tool install --force .
/tmp/mncli-uv-bin/mncli --version
```

## Credits

`mncli-execute-code` is derived from
[`marimo-team/marimo-pair`](https://github.com/marimo-team/marimo-pair)'s
`scripts/execute-code.sh`, licensed under Apache-2.0.

## License

Most of this project is MIT licensed. The bundled `mncli-execute-code`
transport includes code derived from `marimo-team/marimo-pair` under
Apache-2.0. See `THIRD_PARTY_NOTICES.md` and
`licenses/marimo-pair-APACHE-2.0.txt`.
