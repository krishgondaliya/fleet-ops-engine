# SYNTHETIC trip fixture: NOT provider data

`SYNTHETIC_trips.csv` is **made up by hand** for offline tests. It does not come from the Citi Bike trip bucket.

- It uses the real 13-column trip schema (verified on JC-202610) so that parsing is exercised.
- Station IDs JC014, JC115 and JC006 match short_names in the real GBFS fixtures (`../gbfs/`), so the join can be tested. `ZZ999` is deliberately unmatched.
- Station names, coordinates, ride IDs (`SYN##`) and times are invented. They were chosen to cover:
  - SYN01: EDT, so 08:00 local is 12:00 UTC.
  - SYN02: EST, so 08:00 local is 13:00 UTC.
  - SYN03: the ambiguous fall-back hour, 2025-11-02 01:30 local.
  - SYN04: the nonexistent spring-forward hour, 2026-03-08 02:30 local.
  - SYN05: an unmatched start station.
  - SYN06: a missing end station.
