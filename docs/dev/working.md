# How to work on LabelDesk with Claude (full list)

## How the owner wants you to work (from their global preferences)
- Run commands yourself on the technician's PC; ask before anything needing sudo. Say what you ran and where.
- No guessing — check the hardware/CUPS/journal yourself; ask only what you genuinely can't determine.
- Escalate diagnostics fast (journal, `lpstat -t`, `ausearch`, CUPS debug log) instead of repeating guesses.
- Skip pleasantries; be concise; correct them when they're wrong. Re-verify before alarming conclusions.
- Say plainly what was tested and how (real printer vs fake listener vs headless render).
- Customer names are work data: they stay on the PC — never in the repo (it's PUBLIC), no cloud services, no telemetry.
  The only outbound calls: ConnectWise (when ON) and the version check to GitHub after a print (no label content).
- Ship every change through tools/update.sh (see CLAUDE.md → Shipping a change); tick docs/dev/open-items.md.
