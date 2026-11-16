# Platform notes: containers

- **A container image is the preferred way to ship software.** It carries its
  runtime and tools with it, so what was tested is what runs.
- **Packages come from a minimal distribution (Alpine or Wolfi)
  first;** anything not packaged there comes from the tool's official
  upstream image as the source.
- **Cross-platform means macOS and Linux.** Windows is not a design
  target; a local tool or script is tested on both.
