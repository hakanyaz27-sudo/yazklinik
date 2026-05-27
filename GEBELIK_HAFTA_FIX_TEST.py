# -*- coding: utf-8 -*-
"""GEBELIK_HAFTA_FIX_TEST

Dogrular: USG'deki GA olcum anindaki degerdir; guncel hafta bugune ilerletilmelidir.
- _patient_ga_quick_card(key) -> (label, kaynak) bugune gore guncel hafta vermeli.
- Eski tarihli USG'si olan bir hastada current_hafta > scan_hafta olmali (ilerleme).
- Ozellikle 'ebru' iceren hasta varsa onu raporla.
Import-only; server baslatmaz.
"""
import os
import sys

os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
os.environ.setdefault("YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC", "0")
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yazklinik_web as yw  # noqa: E402


def _today():
    from datetime import datetime
    return datetime.now().date()


def main():
    today = _today()
    rows = []
    try:
        with yw.db_conn() as con:
            con.row_factory = lambda cur, row: {
                d[0]: row[i] for i, d in enumerate(cur.description)}
            # Her hasta icin en yeni USG (ga_weeks dolu) + tarih.
            usg = con.execute(
                "SELECT patient_key, usg_date, ga_weeks, ga_days "
                "FROM usg_measurements "
                "WHERE ga_weeks IS NOT NULL "
                "ORDER BY COALESCE(usg_date,'') DESC, id DESC").fetchall()
            seen = {}
            for u in usg:
                k = u.get("patient_key")
                if k and k not in seen:
                    seen[k] = u
            # Isim eslemesi
            names = {}
            try:
                for p in con.execute(
                        "SELECT folder_key, display_name FROM patients").fetchall():
                    names[p.get("folder_key")] = p.get("display_name") or ""
            except Exception:
                pass
            for k, u in seen.items():
                u["display_name"] = names.get(k, "")
                rows.append(u)
    except Exception as exc:
        print("DB_QUERY_FAIL:", repr(exc))
        return 2

    if not rows:
        print("NO_USG_ROWS (gebelik USG kaydi yok) - sentetik mantik testine geciliyor")

    print(f"today={today} | usg'li hasta sayisi={len(rows)}")
    print("-" * 72)

    advanced_ok = 0
    advanced_checked = 0
    ebru_seen = False

    # Once 'ebru', sonra en eski USG'liler
    def _age_days(u):
        d = yw._preg_plan_parse_date_v1000(u.get("usg_date"))
        return (today - d).days if d else -1

    rows_sorted = sorted(rows, key=_age_days, reverse=True)
    show = []
    for u in rows_sorted:
        nm = (u.get("display_name") or "").lower()
        if "ebru" in nm:
            ebru_seen = True
            show.insert(0, u)
        elif len(show) < 8:
            show.append(u)

    for u in show:
        k = u.get("patient_key")
        scan_w = u.get("ga_weeks")
        scan_d = u.get("ga_days") or 0
        usg_day = yw._preg_plan_parse_date_v1000(u.get("usg_date"))
        age_d = (today - usg_day).days if usg_day else None
        try:
            label, src = yw._patient_ga_quick_card(k)
        except Exception as exc:
            label, src = ("HATA:" + repr(exc), "")
        cur_w = None
        try:
            cur_w = int(str(label).split("+")[0]) if label else None
        except Exception:
            cur_w = None
        flag = ""
        if age_d is not None and age_d > 7 and scan_w is not None and cur_w is not None:
            advanced_checked += 1
            if cur_w > int(scan_w):
                advanced_ok += 1
                flag = "OK(ilerledi)"
            elif cur_w == int(scan_w):
                flag = "ESIT(?)"
            else:
                flag = "GERILEDI(!)"
        nm = u.get("display_name") or k
        print(f"{nm[:24]:24} | USG {u.get('usg_date')} scan={scan_w}+{scan_d} "
              f"({age_d} gun once) -> GUNCEL={label} [{src}] {flag}")

    print("-" * 72)
    print(f"ebru_bulundu={ebru_seen} | ilerleme_kontrol={advanced_checked} "
          f"ilerleme_ok={advanced_ok}")

    # --- Ebru + gercek gebe hasta probu (PDF/LMP yolu, usg_measurements bos olsa da) ---
    print("=" * 72)
    cand_keys = []
    try:
        with yw.db_conn() as con:
            con.row_factory = lambda cur, row: {
                d[0]: row[i] for i, d in enumerate(cur.description)}
            # 'ebru' her yerde ara
            for sql in (
                "SELECT folder_key AS k, display_name AS n FROM patients "
                "WHERE LOWER(display_name) LIKE '%ebru%'",
                "SELECT patient_key AS k, '' AS n FROM patient_demographics "
                "WHERE LOWER(patient_key) LIKE '%ebru%'",
            ):
                try:
                    for r in con.execute(sql).fetchall():
                        if r.get("k"):
                            cand_keys.append((r["k"], r.get("n") or ""))
                except Exception:
                    pass
            # lmp_override dolu olan gebe hastalar (gercek LMP yolu testi)
            try:
                for r in con.execute(
                    "SELECT patient_key AS k, lmp_override FROM patient_demographics "
                    "WHERE lmp_override IS NOT NULL AND lmp_override<>'' LIMIT 6"
                ).fetchall():
                    cand_keys.append((r["k"], "LMP=" + str(r.get("lmp_override"))))
            except Exception:
                pass
    except Exception as exc:
        print("PROB_DB_FAIL:", repr(exc))

    if not cand_keys:
        print("EBRU/LMP'li gebe hasta bulunamadi (DB'de yok ya da farkli anahtar).")
    seen_k = set()
    for k, note in cand_keys:
        if k in seen_k:
            continue
        seen_k.add(k)
        try:
            qc = yw._patient_ga_quick_card(k)
        except Exception as exc:
            qc = ("QC_HATA:" + repr(exc), "")
        prof_ga = None
        try:
            prof = yw._diet_profile_v1000(k)
            prof_ga = (prof.get("ga_w"), prof.get("ga_d"), prof.get("edd_str"))
        except Exception as exc:
            prof_ga = ("PROF_HATA:" + repr(exc),)
        print(f"[{note}] key={k}")
        print(f"    quick_card={qc} | diet_profile ga=(w,d,edd)={prof_ga}")

    # Sentetik dogrulama: parse + ilerletme aritmetigi
    from datetime import timedelta
    base = today - timedelta(days=175)  # 25 hafta once
    base_str = base.strftime("%d.%m.%Y")
    parsed = yw._preg_plan_parse_date_v1000(base_str)
    syn_scan_days = 12 * 7 + 0
    syn_cur_days = syn_scan_days + (today - parsed).days if parsed else None
    syn_cur_w = syn_cur_days // 7 if syn_cur_days else None
    print(f"SENTETIK: 12+0 USG 175 gun once -> guncel ~{syn_cur_w} hafta "
          f"(beklenen ~37) parse_ok={parsed is not None}")

    ok = (parsed is not None and syn_cur_w == 37
          and (advanced_checked == 0 or advanced_ok == advanced_checked))
    print("GEBELIK_HAFTA_FIX_TEST", "OK" if ok else "DIKKAT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
