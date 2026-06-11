const CROP = "w=160&h=160&fit=crop&crop=face";

/** Verified working Unsplash doctor headshots only. */
const MALE_PLACEHOLDER_PHOTOS = [
  `https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?${CROP}`,
  `https://images.unsplash.com/photo-1559839734-2b71ea197ec2?${CROP}`,
  `https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?${CROP}`,
  `https://images.unsplash.com/photo-1560250097-0b93528c311a?${CROP}`,
  `https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?${CROP}`,
];

const FEMALE_PLACEHOLDER_PHOTOS = [
  `https://images.unsplash.com/photo-1594824476967-48c8b964273f?${CROP}`,
  `https://images.unsplash.com/photo-1551601651-2a8555f1a136?${CROP}`,
  `https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?${CROP}`,
  `https://images.unsplash.com/photo-1584982751601-97dcc096659c?${CROP}`,
  `https://images.unsplash.com/photo-1594824476967-48c8b964273f?${CROP}&sat=-20`,
];

const FEMALE_FIRST_NAMES = new Set([
  "anita", "priya", "meera", "kavita", "lakshmi", "deepa", "anjali", "neha", "pooja",
  "shalini", "divya", "ritu", "sneha", "nandini", "lata", "sunita", "pallavi", "rekha",
  "jyoti", "nisha", "swati", "radhika", "kiran", "ishita", "smita", "leela", "farah",
  "uma", "bharti", "shweta", "madhuri", "geeta", "parul", "alka", "christina",
]);

export function isLegacyCartoonAvatar(url?: string | null): boolean {
  if (!url) return false;
  const lowered = url.toLowerCase();
  return lowered.includes("dicebear.com") || lowered.includes("avataaars");
}

export function isUploadedProfilePhoto(url?: string | null): boolean {
  if (!url || isLegacyCartoonAvatar(url)) return false;
  const lowered = url.toLowerCase();
  return !lowered.includes("images.unsplash.com") && !lowered.includes("dicebear.com");
}

function pickFromPool(seed: string, pool: string[]): string {
  let idx = 0;
  for (const ch of seed) idx = (idx + ch.charCodeAt(0)) % pool.length;
  return pool[idx];
}

export function doctorInitials(name: string): string {
  const parts = name.replace(/^Dr\.\s*/i, "").trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? "D").toUpperCase();
}

function defaultDoctorAvatarUrl(name: string): string {
  const first = name.replace(/^Dr\.\s*/i, "").trim().split(/\s+/)[0]?.toLowerCase() ?? "";
  const pool = FEMALE_FIRST_NAMES.has(first) ? FEMALE_PLACEHOLDER_PHOTOS : MALE_PLACEHOLDER_PHOTOS;
  return pickFromPool(name, pool);
}

/** Uploaded photo when available; otherwise a professional doctor placeholder. */
export function resolveDoctorProfileImage(name: string, url?: string | null): string {
  if (isUploadedProfilePhoto(url)) return url!;
  return defaultDoctorAvatarUrl(name || "Doctor");
}
