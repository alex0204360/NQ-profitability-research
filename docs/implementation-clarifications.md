# Clarifications before any V2 outcome evaluation

These details resolve implementation conventions without changing the frozen
statistical gates or examining outcomes.

- Book each complete trade's net P&L and count to its ET entry date for paired
  daily inference. These are entry-date cohort P&L series, not intraday
  mark-to-market account equity. This keeps all trades in the fixed calendar frame,
  including an exit at the final permitted period boundary. All support dates and
  weeks also use entry dates. Closed-trade drawdown follows chronological exits.
- Feature timestamps are canonical bar starts; encoder timestamps and entry dates
  use their corresponding decision close (start plus one minute).
- Canonical action ordering is H, SL multiple, TP multiple, direction long then
  short, implementing the plan's tie-break rule without relying on unstable sorts.
- Recorded exit time is the resolving bar's close, including an opening-gap
  resolution. This conservatively prevents another order inside that same bar.
- Frozen calendar spans may be supplied by a caller or omitted by the generic
  matcher; research replay always supplies the audited schedule. Without a known
  close the matcher enforces only the 45-minute cap and labels its recommendation
  as lacking a supplied closure boundary. No live calendar connection is added.
