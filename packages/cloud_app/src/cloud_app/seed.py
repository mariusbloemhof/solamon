"""Bench-MVP seed: 1 org, 1 admin, 1 site, 1 Acuvim L device + logical metrics.

Idempotent — safe to run repeatedly. The seed prints the device UUID at the
end; copy that into BENCH_DEVICE_ID for the composition root.

Configurable via env:
    DATABASE_URL              postgres://... (required)
    BENCH_ORG_SLUG            default: bench-org
    BENCH_SITE_SLUG           default: bench
    BENCH_DEVICE_NAME         default: Acuvim-bench
    BENCH_ADMIN_EMAIL         default: admin@bench.example.com
    BENCH_ADMIN_PASSWORD      default: hunter2
    BENCH_MQTT_USERNAME       default: solamon-bench
    BENCH_MQTT_PASSWORD       default: change-me
    LOGICAL_METRICS_PATH      default: architecture/logical_metrics.yaml
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

from profile_loader.loader import ProfileLoader

from .auth.passwords import hash_password
from .db.migrations import run_migrations
from .db.pool import create_pool


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _repo_root() -> Path:
    # .../packages/cloud_app/src/cloud_app/seed.py → .../
    return Path(__file__).resolve().parents[4]


async def seed_bench() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)

    org_slug          = _env("BENCH_ORG_SLUG",     "bench-org")
    site_slug         = _env("BENCH_SITE_SLUG",    "bench")
    device_name       = _env("BENCH_DEVICE_NAME",  "Acuvim-bench")
    admin_email       = _env("BENCH_ADMIN_EMAIL", "admin@bench.example.com")
    admin_password    = _env("BENCH_ADMIN_PASSWORD", "hunter2")
    mqtt_username     = _env("BENCH_MQTT_USERNAME", "solamon-bench")
    mqtt_password     = _env("BENCH_MQTT_PASSWORD", "change-me")
    catalog_path      = _env("LOGICAL_METRICS_PATH",
                             str(_repo_root() / "architecture" / "logical_metrics.yaml"))

    pool = await create_pool(database_url, min_size=1, max_size=2)
    try:
        await run_migrations(pool)
        async with pool.acquire() as conn:
            # 1. Logical metric catalog — populated from the YAML so the
            #    Acuvim adapter's keys all resolve to a known data_type.
            #    Pass schema_dir so the loader works in containers / venvs
            #    where its workspace-relative DEFAULT_SCHEMA_DIR doesn't
            #    resolve. Schemas live alongside the YAML.
            catalog = ProfileLoader(
                schema_dir=Path(catalog_path).parent,
            ).load_catalog(catalog_path)
            for m in catalog.all():
                await conn.execute(
                    """INSERT INTO app.logical_metric
                         (key, label, unit, data_type, category, is_cumulative,
                          monotonic, direction_convention,
                          expected_range_min, expected_range_max,
                          is_writable, allowed_values, enum_values)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                       ON CONFLICT (key) DO NOTHING""",
                    m.key, m.label, m.unit, m.data_type, m.category, m.is_cumulative,
                    m.monotonic, m.direction_convention,
                    m.expected_range[0] if m.expected_range else None,
                    m.expected_range[1] if m.expected_range else None,
                    m.is_writable,
                    m.allowed_values, m.enum_values,
                )

            # 2. Organisation.
            org_id = await conn.fetchval(
                """INSERT INTO app.organisation (id, name, slug)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                uuid4(), "Bench Org", org_slug,
            )

            # 3. Admin user.
            admin_id = await conn.fetchval(
                """INSERT INTO app.users
                     (id, organisation_id, email, display_name, password_hash, tier, role)
                   VALUES ($1, $2, $3, 'Bench Admin', $4, 'operations', 'admin')
                   ON CONFLICT (email) DO UPDATE
                     SET password_hash = EXCLUDED.password_hash
                   RETURNING id""",
                uuid4(), org_id, admin_email, hash_password(admin_password),
            )

            # 4. Site.
            site_id = await conn.fetchval(
                """INSERT INTO app.site
                     (id, organisation_id, name, slug, mqtt_username, mqtt_password)
                   VALUES ($1, $2, 'Bench', $3, $4, $5)
                   ON CONFLICT (slug) DO UPDATE
                     SET mqtt_username = EXCLUDED.mqtt_username,
                         mqtt_password = EXCLUDED.mqtt_password
                   RETURNING id""",
                uuid4(), org_id, site_slug, mqtt_username, mqtt_password,
            )

            # 5. Device type — Acuvim L.
            type_id = await conn.fetchval(
                """INSERT INTO app.device_type
                     (id, manufacturer, model, category, profile_slug, profile_yaml)
                   VALUES ($1, 'AccuEnergy', 'Acuvim L', 'meter', 'acuvim_l', '{}'::jsonb)
                   ON CONFLICT (profile_slug) DO UPDATE
                     SET manufacturer = EXCLUDED.manufacturer
                   RETURNING id""",
                uuid4(),
            )

            # 6. Device — the bench Acuvim. host/port/unit_id are placeholders;
            #    the meter pushes via MQTT, we don't poll it.
            device_id = await conn.fetchval(
                """INSERT INTO app.device
                     (id, site_id, device_type_id, name, host, port, unit_id, is_billing_source)
                   VALUES ($1, $2, $3, $4, '192.168.1.254', 502, 1, true)
                   ON CONFLICT (site_id, name) DO UPDATE
                     SET device_type_id = EXCLUDED.device_type_id
                   RETURNING id""",
                uuid4(), site_id, type_id, device_name,
            )

            # 7. Grant admin access to site.
            await conn.execute(
                """INSERT INTO app.site_access (user_id, site_id, access_level)
                   VALUES ($1, $2, 'admin')
                   ON CONFLICT (user_id, site_id) DO NOTHING""",
                admin_id, site_id,
            )

        print()
        print("════════════════════════════════════════════════════════════════════")
        print("  Bench seed complete")
        print("════════════════════════════════════════════════════════════════════")
        print(f"  Site slug      : {site_slug}")
        print(f"  Device name    : {device_name}")
        print(f"  Device UUID    : {device_id}        ← set BENCH_DEVICE_ID to this")
        print(f"  Admin email    : {admin_email}")
        print(f"  Admin password : {admin_password}")
        print(f"  Logical metrics: {len(catalog.all())} loaded from {Path(catalog_path).name}")
        print("════════════════════════════════════════════════════════════════════")
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(seed_bench())


if __name__ == "__main__":
    main()
