<p align="center"><image src="assets/logo.svg" height="128" alt="Logwarp" /></p>

<h1 align="center">Logwarp</h1>

<p align="center">
<strong>Log file processing library which applies DSP to your logs.</strong><br />
Visualize, filter, analyze, and find anomalies in your log files, gaining real
understanding and insights in seconds. Local-first, command line-friendly.
</p>

<p align="center"><img width="600" height="338" alt="logwarp" src="https://github.com/user-attachments/assets/94140318-326d-4c3f-9f25-0c350bc125d1" /></p>

Logwarp is a Python library developed based on decades of reading, analyzing,
correlating, and otherwise digging through log files - from simple `printf` over
serial port to gigabytes of traces.
v
Logwarp treats log files as signals carrying information, and applies good'ol
DSP to process that information. Find distinctive log lines as signal peaks,
apply low-pass filters to get rid of the noise, use FFT to find repeating
sequences of messages, and more.

## Download

Install using pip:

```shell
pip install logwarp
```

## Quick Start

### Command Line Interface

Logwarp's command line is structured using commands, with a few options common
for all commands:

```bash
-i, --input FILE    Path to the input log file.
-w, --write         Write results to files using the naming scheme:
                    <original_file>_logwarp_<operation>_<index>.<ext>
-o, --stdout        Print results to stdout.
-Y, --yaml          Format output as YAML.
-j, --json          Format output as JSON.
-n, --line-numbers  Show original line numbers in the results.
```

For example, splitting a log file by token 5th (tokens in this context are
groups of characters delimited by space), with output written to the `stdout` as
JSON:

```bash
> logwarp -i src/docs/samples/journal.log -j split 4
{
  "outliers": [
    "-- Boot 65d7a8f0c2a846c09aa0a7af806cc7c9 --",
    "CoolerControlD 2.2.2",
    "-- Boot 6ab2431495de4493b3f57cd86e06f666 --",
    "CoolerControlD 2.2.2",
    "qrc:/qt/qml/org/kde/kirigami/layouts/FormLayout.qml:72:5",
    "qrc:/qt/qml/org/kde/kirigami/layouts/FormLayout.qml:72:5",
    ... # output continues
```

Search through the file for distinctive log entries, printing out line numbers:

```bash
> logwarp -i src/docs/samples/journal.log find distinctive -n
727 |> paź 04 16:43:10 garuda systemd[1]: systemd 258-4-arch running in system mode (+PAM +AUDIT -SELINUX +APPARMOR -IMA +IPE +SMACK +SECCOMP +GCRYPT +GNUTLS +OPENSSL +ACL +BLKID +CURL +ELFUTILS +FIDO2 +IDN2 -IDN +IPTC +KMOD +LIBCRYPTSETUP +LIBCRYPTSETUP_PLUGINS+LIBFDISK +PCRE2 +PWQUALITY +P11KIT +QRENCODE +TPM2 +BZIP2 +LZ4 +XZ +ZLIB +ZSTD +BPF_FRAMEWORK +BTF +XKBCOMMON +UTMP -SYSVINIT +LIBARCHIVE)
... # output continues
```

Find log lines similar to a specific fragment, in this example, to lines from
10849 to 10853:

```bash
> logwarp -i src/docs/samples/journal.log find similar 10849,10853 --step=2 -n
5385 |> paź 04 16:58:20 garuda kernel: Bluetooth: hci0: command 0xfc61 tx timeout
5513 |> paź 04 16:58:49 garuda systemd[1578]: Reached target Bluetooth.
5520 |> paź 04 16:58:51 garuda kernel: usb 1-1.1: reset full-speed USB device number 6 using xhci_hcd
5555 |> paź 04 16:58:59 garuda systemd[1578]: Stopped target Bluetooth.
6156 |> paź 04 17:01:25 garuda kernel: Bluetooth: hci0: RTL: RTL: Read reg16 failed (-110)
6296 |> paź 04 17:01:58 garuda systemd[1]: Reached target Bluetooth Support.
```

### Python API

Check out the [Introduction](src/docs/introduction.ipynb) for semi-interactive
guide to using Logwarp's API from Python.

## Roadmap

Also known as "things I wish I had when digging through a log file":

- [x] ~~unravel (split) log files by fixed slice of each line, by token, or by regex~~
- [x] ~~vectorization and similarity search~~
- [x] ~~peak detection (finding distinctive fragments of the file)~~
- [ ] merge (weave) log files on timestamps
- [ ] command line interface
- [ ] detection of repeating messages using FFA
- [ ] frequency analysis with FFT
- [ ] frequency filtering
- [ ] inverse FFT transform
- [ ] automatic detection of repeating blocks and sequences
- [ ] log file annotations
- [ ] automatic creation of flow diagrams from detected blocks and annotations
- [ ] similarity diff (diff the vectorized versions of the files)
- [ ] MCP server and/or plugins for agents
- [ ] GUI
- [ ] TUI
- [ ] VSCode extension, maybe?
