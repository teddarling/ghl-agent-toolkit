# Demo: read commands and a dry-run tagging pass, all in demo mode (no credentials).
# Render with vhs (https://github.com/charmbracelet/vhs — `brew install vhs`):
#     vhs examples/tapes/demo-cli.tape
Output docs/assets/demo-cli.gif

Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set TypingSpeed 35ms

Type "export GHL_DEMO_MODE=1"
Enter
Sleep 500ms

Type "uv run ghl contacts list"
Enter
Sleep 3s

Type "uv run ghl agent tag --dry-run"
Enter
Sleep 6s
