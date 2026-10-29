"""HL7 v2 laboratory message adapter. Sandbox ORU^R01 parser only — not a full interface engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedLabResult:
    external_message_id: str
    patient_external_id: str
    patient_name: str
    order_id: str
    test_code: str
    test_name: str
    value: str
    unit: str
    reference_range: str
    abnormal_flag: str
    result_status: str  # preliminary | final | corrected | cancelled
    observation_datetime: str
    raw_summary: dict[str, Any]


class Hl7LabPort:
    def parse_oru_r01(self, message: str) -> ParsedLabResult: ...


class FakeHl7LabAdapter:
    """Parses a minimal pipe-delimited ORU^R01 sandbox payload."""

    provider = "fake-hl7"

    def parse_oru_r01(self, message: str) -> ParsedLabResult:
        lines = [line.strip() for line in message.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
        msh = next((line for line in lines if line.startswith("MSH")), "")
        pid = next((line for line in lines if line.startswith("PID")), "")
        obr = next((line for line in lines if line.startswith("OBR")), "")
        obx = next((line for line in lines if line.startswith("OBX")), "")
        if not msh or not pid or not obx:
            raise ValueError("Sandbox ORU requires MSH, PID, and OBX segments.")

        def field(segment: str, index: int) -> str:
            parts = segment.split("|")
            return parts[index] if len(parts) > index else ""

        msg_id = field(msh, 9) or field(msh, 10) or "MSG-UNKNOWN"
        # PID-3 patient id, PID-5 name
        patient_id = field(pid, 3).split("^")[0] or "EXT-UNKNOWN"
        patient_name = field(pid, 5).replace("^", " ").strip() or "Unknown Patient"
        order_id = field(obr, 2) or field(obr, 3) or ""
        # OBX-3 code^name, OBX-5 value, OBX-6 unit, OBX-7 range, OBX-8 flag, OBX-11 status, OBX-14 datetime
        code_field = field(obx, 3)
        code_parts = code_field.split("^")
        test_code = code_parts[0] or "UNK"
        test_name = code_parts[1] if len(code_parts) > 1 else test_code
        value = field(obx, 5)
        unit = field(obx, 6)
        ref = field(obx, 7)
        flag = field(obx, 8)
        status_code = field(obx, 11).upper() or "F"
        status_map = {"P": "preliminary", "F": "final", "C": "corrected", "X": "cancelled"}
        result_status = status_map.get(status_code, "final")
        obs_dt = field(obx, 14) or field(obr, 7) or ""
        return ParsedLabResult(
            external_message_id=msg_id,
            patient_external_id=patient_id,
            patient_name=patient_name,
            order_id=order_id,
            test_code=test_code,
            test_name=test_name,
            value=value,
            unit=unit,
            reference_range=ref,
            abnormal_flag=flag,
            result_status=result_status,
            observation_datetime=obs_dt,
            raw_summary={
                "segments": [line[:3] for line in lines],
                "note": "Sandbox parse — not a certified HL7 interface.",
            },
        )


def build_hl7_lab_adapter() -> FakeHl7LabAdapter:
    return FakeHl7LabAdapter()
