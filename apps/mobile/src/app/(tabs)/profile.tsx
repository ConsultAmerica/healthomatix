import { PatientPage, StatusCard } from "../../components/PatientPage";

export default function ProfileScreen() {
  return (
    <PatientPage
      eyebrow="PROFILE"
      title="Your account"
      description="Profile and consent details stay unavailable until a patient session is established."
    >
      <StatusCard
        title="Account and consent"
        detail="This preview does not load or change personal information or consent."
        status="SIGN-IN REQUIRED"
      />
    </PatientPage>
  );
}
