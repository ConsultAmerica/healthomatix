"""HIPAA-eligible video provider port. Fake adapter for CI; live providers require a BAA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class VideoRoom:
    provider: str
    room_id: str
    join_url: str


@dataclass(frozen=True)
class VideoParticipantToken:
    role: str  # patient | clinician
    token: str
    join_url: str
    expires_in_seconds: int


class VideoPort(Protocol):
    def create_room(self, *, session_id: str, appointment_id: str) -> VideoRoom: ...

    def participant_token(
        self,
        *,
        room: VideoRoom,
        user_id: str,
        role: str,
        display_name: str,
    ) -> VideoParticipantToken: ...

    def end_session(self, *, room: VideoRoom) -> None: ...

    def revoke_participant(self, *, room: VideoRoom, user_id: str) -> None: ...


class FakeVideoAdapter:
    """
    Deterministic in-process video stub for tests and local demos.
    Production must use Daily, LiveKit, Vonage, or Amazon Chime under a signed BAA.
    Do not use Twilio Programmable Video (sunset).
    """

    provider = "fake"

    def create_room(self, *, session_id: str, appointment_id: str) -> VideoRoom:
        room_id = f"hmx-{session_id[:8]}-{appointment_id[:8]}"
        return VideoRoom(
            provider=self.provider,
            room_id=room_id,
            join_url=f"https://video.healthomatix.local/rooms/{room_id}",
        )

    def participant_token(
        self,
        *,
        room: VideoRoom,
        user_id: str,
        role: str,
        display_name: str,
    ) -> VideoParticipantToken:
        token = f"fake.{role}.{user_id[:8]}.{uuid4().hex[:12]}"
        return VideoParticipantToken(
            role=role,
            token=token,
            join_url=f"{room.join_url}?role={role}&token={token}",
            expires_in_seconds=3600,
        )

    def end_session(self, *, room: VideoRoom) -> None:
        return None

    def revoke_participant(self, *, room: VideoRoom, user_id: str) -> None:
        return None


def build_video_adapter() -> VideoPort:
    # Wire Daily/LiveKit/Vonage/Chime here when BAA credentials are configured.
    return FakeVideoAdapter()
