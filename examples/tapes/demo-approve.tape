# Demo: the full propose → approve → apply loop with interactive approval,
# in demo mode (no credentials, no live writes — the demo transport absorbs them).
# Render with vhs (https://github.com/charmbracelet/vhs — `brew install vhs`):
#     vhs examples/tapes/demo-approve.tape
Output docs/assets/demo-approve.gif

Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 12
Set TypingSpeed 35ms

Type "export GHL_DEMO_MODE=1"
Enter
Sleep 500ms

Type "uv run ghl agent tag --apply"
Enter
Sleep 5s

Type "y"
Enter
Sleep 2s

Type "y"
Enter
Sleep 2s

Type "n"
Enter
Sleep 3s
