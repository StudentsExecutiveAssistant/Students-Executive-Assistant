"""Запуск повного набору тестів та генерація зразків .docx у tests/out/."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    from tests.helpers import OUT_DIR, STUDS_IARD_4, STUDS_IBIB_4
    from tests.test_bot_flow import (
        test_admin_flow_in_memory,
        test_bot_dmode_flow_in_memory,
        test_dlya_parsing_and_resp_badges_in_memory,
        test_parse_user_ids,
    )
    from tests.test_cleaners import (
        test_clean_purpose_and_names,
        test_normalize_students,
        test_reason_and_preposition_parsing_in_memory,
    )
    from tests.test_dates import test_dates_and_schedule_in_memory
    from tests.test_docx_builder import (
        _sample_absence_ikni_37,
        _sample_absence_ikta_21,
        _sample_guest_names,
        _sample_rooms_ntb,
        check_inline_4,
        test_absence_thresholds_in_memory,
        test_audience_weekdays_and_purchase_fund_in_memory,
        test_config_and_award_in_memory,
        test_photo_templates_in_memory,
        test_sport_inventory_in_memory,
        test_with_appendix_num_and_batch_in_memory,
    )
    from tests.test_validator import test_text_issues_diagnostics, test_timed_templates_and_checker_in_memory

    test_normalize_students()
    test_clean_purpose_and_names()
    test_reason_and_preposition_parsing_in_memory()
    test_dates_and_schedule_in_memory()
    test_absence_thresholds_in_memory()
    test_with_appendix_num_and_batch_in_memory()
    test_photo_templates_in_memory()
    test_sport_inventory_in_memory()
    test_config_and_award_in_memory()
    test_audience_weekdays_and_purchase_fund_in_memory()
    test_timed_templates_and_checker_in_memory()
    test_text_issues_diagnostics()
    test_bot_dmode_flow_in_memory()
    test_dlya_parsing_and_resp_badges_in_memory()
    test_parse_user_ids()
    test_admin_flow_in_memory()

    outputs = {
        OUT_DIR / "01_rooms_ntb.docx": _sample_rooms_ntb(),
        OUT_DIR / "02_absence_ikta_21.docx": _sample_absence_ikta_21(),
        OUT_DIR / "03_absence_ikni_37.docx": _sample_absence_ikni_37(),
        OUT_DIR / "04_absence_ibib_4.docx": check_inline_4("ІБІБ", STUDS_IBIB_4),
        OUT_DIR / "05_absence_iard_4.docx": check_inline_4("ІАРД", STUDS_IARD_4),
        OUT_DIR / "06_guest_platskart.docx": _sample_guest_names(),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, data in outputs.items():
        path.write_bytes(data)
    print("All .docx tests passed!")
    for path in outputs:
        print(f"Wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
