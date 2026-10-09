# Future work

Living list. Newest icebox items at the top. Move a row to **Done** only after it ships on `main`.

## Icebox

Not scheduled. Do not start these on a release PR.

| Item | Notes |
| ---- | ----- |
| TrueNAS **Install via YAML** | Custom App wizard + image `CMD` `python -m src.stack` is the current deploy. Compose YAML would run Redis + API + family bot + admin as separate containers (closer to laptop `docker compose up`). Needs a NAS-specific compose (GHCR `image:`, host paths), not a paste of `docker-compose.yml`. Revisit after `0.4.1` is stable in production. |
| Pause reminders | Skip or snooze medication reminders for a date range (travel, leave). |
| Timezone UX | App TZ is `TIMEZONE` (default `Asia/Singapore`). No per-user TZ or “what TZ is this reminder?” in the family bot. |
| Who missed today | Notify admin (or family) when today’s reminder was sent and not acknowledged. |

## After `0.4.1` is on production

Ops, not a code feature: pin TrueNAS production to `ghcr.io/d95tan/bb_bot:0.4.1` (leave `0.3.1` until that tag exists). Custom App Command = image default. Once the admin bot is polling, remove the admin Telegram id from `TELEGRAM_USER_IDS` so family reminders only go to the family bot.

## Done (recent)

| Item | Where |
| ---- | ----- |
| Combined image `CMD` for one TrueNAS container | `src.stack`, `0.4.1` |
| Family `/help` Markdown + admin help/auth | `0.4.0`+staging fixes |
| Admin Telegram bot | `0.4.0` |
| GHCR `staging` from `develop` | `0.4.0` |
| FastAPI + thin user-bot | `0.4.0` |
| Off-day medication reminders | `0.4.0` |
