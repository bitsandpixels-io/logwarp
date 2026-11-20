<p align="center"><image src="assets/logo.svg" height="128" alt="Logwarp" /></p>

<h1 align="center">Logwarp</h1>

<p align="center">
<strong>Log file processing library which applies DSP to your logs.</strong><br />
Visualize, filter, analyze, and find anomalies in your log files, gaining real
understanding and insights in seconds. Local-first, command line-friendly.
</p>

<p align="center"><img src="https://bitsandpixels.io/logwarp.gif" width="720" /></p>

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

Check out the [Introduction](src/docs/introduction.ipynb) for semi-interactive
guide to using Logwarp.

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
