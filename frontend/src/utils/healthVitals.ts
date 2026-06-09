export interface HealthVital {
  key: string;
  label: string;
  value: string;
  value_secondary?: string | null;
  display: string;
  unit: string;
  status: string;
  flag: string;
  bar_percent: number;
  icon: string;
  icon_variant: "teal" | "rose" | "cyan";
  bar_class: string;
  source_report_id?: string | null;
  source_filename?: string | null;
}

export interface HealthVitalsResponse {
  vitals: HealthVital[];
  has_data: boolean;
}
