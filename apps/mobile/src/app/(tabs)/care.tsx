import { PatientPage, StatusCard } from "../../components/PatientPage";

export default function CareScreen() {
  return (
    <PatientPage
      eyebrow="CARE"
      title="Your care team"
      description="Clinic and provider details are only shown after an authorized clinic connection."
    >
      <StatusCard
        title="Clinic connection"
        detail="Accepting a clinic invitation is not available in this preview."
        status="SIGN-IN REQUIRED"
      />
      <StatusCard
        title="Provider directory"
        detail="Provider discovery and appointment booking are not active here."
        status="UNAVAILABLE"
      />
    </PatientPage>
  );
}
