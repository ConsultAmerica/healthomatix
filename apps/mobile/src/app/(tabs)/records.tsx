import { PatientPage, StatusCard } from "../../components/PatientPage";

export default function RecordsScreen() {
  return (
    <PatientPage
      eyebrow="RECORDS"
      title="Your records"
      description="Private document access is unavailable until secure storage and sign-in are configured."
    >
      <StatusCard
        title="Documents"
        detail="No records are displayed or fabricated in this preview."
        status="STORAGE NOT CONFIGURED"
      />
    </PatientPage>
  );
}
