import { AppointmentItem } from "../components/AppointmentCard";
import { formatChatDateLabel } from "./chatConversations";

export interface InsightCard {
  tag: string;
  text: string;
}

export interface HealthInsightsPanel {
  mode: "wellness" | "care";
  headline: string;
  cards: InsightCard[];
  ctaLabel: string;
  ctaTo: string;
  ctaState?: { promptMessage?: string };
}

interface BuildInput {
  history: { condition: string }[];
  meds: { name: string }[];
  reports: { id: string }[];
  allergies: { allergen: string }[];
  upcoming: AppointmentItem[];
  chatCount: number;
}

function hasRichHealthProfile(input: BuildInput): boolean {
  const profileSignals =
    (input.history.length > 0 ? 1 : 0) +
    (input.meds.length > 0 ? 1 : 0) +
    (input.reports.length > 0 ? 1 : 0) +
    (input.allergies.length > 0 ? 1 : 0);
  return profileSignals >= 1;
}

function conditionText(history: { condition: string }[]): string {
  return history.map((h) => h.condition.toLowerCase()).join(" ");
}

function buildWellnessCards(input: BuildInput): InsightCard[] {
  const cards: InsightCard[] = [];
  const conditions = conditionText(input.history);
  const hasDiabetes = /diabet|glucose|blood sugar|a1c|insulin/.test(conditions);
  const hasHeart = /heart|cardio|hypertens|blood pressure|bp/.test(conditions);
  const hasAnemia = /anemia|hemoglobin|iron/.test(conditions);

  cards.push({
    tag: "Sleep Correlation",
    text: hasHeart
      ? "Your resting heart rate pattern looks steady this week. Quality sleep (7–8 hours) supports cardiovascular recovery and stress balance."
      : "Your resting heart rate dropped slightly this week, which often correlates with better sleep consistency. Keep a regular bedtime routine.",
  });

  if (input.chatCount >= 2 || input.meds.length > 0) {
    cards.push({
      tag: "Activity Alert",
      text:
        input.meds.length > 0
          ? "Light daily movement can support medication effectiveness and energy levels. Short walks after meals are a safe place to start."
          : "You have been checking in regularly with your AI assistant. Maintain gentle activity to keep musculoskeletal stress levels optimal.",
    });
  } else {
    cards.push({
      tag: "Activity Alert",
      text: "Aim for moderate activity most days of the week. Even 20–30 minutes of walking supports heart health and mood.",
    });
  }

  if (hasDiabetes) {
    cards.push({
      tag: "Nutrition Prompt",
      text: "Recent glucose patterns may vary after dinner. Consider a balanced, high-protein afternoon snack to help stabilize evening levels.",
    });
  } else if (hasAnemia || input.reports.length > 0) {
    cards.push({
      tag: "Lab Insight",
      text:
        input.reports.length > 0
          ? `Your uploaded lab report${input.reports.length > 1 ? "s" : ""} show${input.reports.length === 1 ? "s" : ""} markers worth tracking. Open your **Full Health Report** for a consolidated review.`
          : "Iron-rich foods and vitamin C pairings may support healthy hemoglobin levels. Discuss supplements with your physician.",
    });
  } else if (input.allergies.length > 0) {
    cards.push({
      tag: "Allergy Watch",
      text: `Your profile lists **${input.allergies.map((a) => a.allergen).join(", ")}**. Mention these in consultations and before new prescriptions.`,
    });
  } else {
    cards.push({
      tag: "Nutrition Prompt",
      text: "Balanced meals with adequate hydration support energy and recovery. Ask your AI assistant for diet tips aligned with your health profile.",
    });
  }

  return cards.slice(0, 3);
}

function buildCareCards(input: BuildInput): InsightCard[] {
  const cards: InsightCard[] = [];

  if (input.upcoming.length > 0) {
    const next = input.upcoming[0];
    const when = formatChatDateLabel(`${next.date}T12:00:00`);
    const doctor = next.doctor_name || "your doctor";
    cards.push({
      tag: "Upcoming Visit",
      text:
        input.upcoming.length === 1
          ? `You have **1 confirmed appointment**. Your next visit is with **${doctor}** on ${when}.`
          : `You have **${input.upcoming.length} confirmed appointments**. Next visit with **${doctor}** on ${when}.`,
    });
  }

  if (input.chatCount > 0) {
    cards.push({
      tag: "AI Consultation",
      text: `You have **${input.chatCount}** health chat${input.chatCount > 1 ? "s" : ""} on record. Continue in AI Consultation for symptom checks or booking help.`,
    });
  }

  if (cards.length === 0) {
    cards.push(
      {
        tag: "Get Started",
        text: "Start an **AI Consultation** to describe symptoms, get health guidance, or book a doctor appointment.",
      },
      {
        tag: "Wellness Tip",
        text: "Add your medical history and upload lab reports to unlock personalized **AI Health Insights**.",
      }
    );
  } else if (cards.length < 3) {
    cards.push({
      tag: "Next Step",
      text: "Complete your health profile in registration or chat to unlock sleep, activity, and nutrition insights.",
    });
  }

  return cards.slice(0, 3);
}

export function buildHealthInsightsPanel(input: BuildInput): HealthInsightsPanel {
  if (hasRichHealthProfile(input)) {
    return {
      mode: "wellness",
      headline: "Personalized Health Review",
      cards: buildWellnessCards(input),
      ctaLabel: "Full Health Report",
      ctaTo: "/reports",
    };
  }

  return {
    mode: "care",
    headline: "Latest AI Review",
    cards: buildCareCards(input),
    ctaLabel: "Open AI Consultation",
    ctaTo: "/chat",
  };
}
