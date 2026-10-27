import { PatientPage, StatusCard } from "../../components/PatientPage";

export default function MessagesScreen() {
  return (
    <PatientPage
      eyebrow="MESSAGES"
      title="Clinic messages"
      description="Secure messaging is a future module and is not enabled."
    >
      <StatusCard
        title="Conversations"
        detail="There are no conversations or message controls in this preview."
        status="PLANNED"
      />
    </PatientPage>
  );
}
