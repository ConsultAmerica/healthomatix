import type { ReactNode } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

const colors = {
  aubergine: "#40223f",
  ivory: "#faf8f4",
  white: "#ffffff",
  muted: "#756c76",
  border: "#e9e2dd",
  gold: "#9b7b45",
  alert: "#f4eee3",
};

type PatientPageProps = {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
};

export function PatientPage({
  eyebrow,
  title,
  description,
  children,
}: PatientPageProps) {
  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.brand}>healthomatix.</Text>
        <Text style={styles.eyebrow}>{eyebrow}</Text>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        <Text style={styles.description}>{description}</Text>
        <View accessibilityRole="alert" style={styles.notice}>
          <Text style={styles.noticeTitle}>Preview — secure sign-in is not configured</Text>
          <Text style={styles.noticeText}>
            This app does not access clinic accounts or patient records. No actions here
            create appointments, send messages, or upload documents.
          </Text>
        </View>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function StatusCard({
  title,
  detail,
  status,
}: {
  title: string;
  detail: string;
  status: string;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardDetail}>{detail}</Text>
      <Text style={styles.status}>{status}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.ivory,
  },
  content: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 36,
    gap: 14,
  },
  brand: {
    color: colors.aubergine,
    fontSize: 20,
    fontWeight: "700",
    letterSpacing: -0.5,
    marginBottom: 14,
  },
  eyebrow: {
    color: colors.gold,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.2,
  },
  title: {
    color: colors.aubergine,
    fontSize: 32,
    fontWeight: "700",
    lineHeight: 39,
  },
  description: {
    color: colors.muted,
    fontSize: 16,
    lineHeight: 24,
  },
  notice: {
    backgroundColor: colors.alert,
    borderColor: "#e6d9c2",
    borderRadius: 14,
    borderWidth: 1,
    gap: 7,
    marginTop: 8,
    padding: 16,
  },
  noticeTitle: {
    color: colors.aubergine,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  noticeText: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 20,
  },
  card: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    gap: 7,
    padding: 16,
  },
  cardTitle: {
    color: colors.aubergine,
    fontSize: 16,
    fontWeight: "700",
  },
  cardDetail: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
  },
  status: {
    color: colors.gold,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.6,
    marginTop: 3,
  },
});
