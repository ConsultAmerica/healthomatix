import { PatientPage, StatusCard } from "../../components/PatientPage";

export default function HomeScreen() {
  return (
    <PatientPage
      eyebrow="PATIENT SPACE"
      title="Your care, connected."
      description="A calm place to stay connected with your clinic."
    >
      <StatusCard
        title="Clinic connection"
        detail="Your clinic information will appear after secure sign-in is available."
        status="NOT CONNECTED"
      />
      <StatusCard
        title="Appointments"
        detail="No appointments are loaded in this preview."
        status="UNAVAILABLE"
      />
    </PatientPage>
  );
}
