"""MediAI doctor catalog — 5+ profiles per major specialty with full metadata."""
from __future__ import annotations

from dataclasses import dataclass

from app.utils.doctor_avatar import default_doctor_avatar_url


@dataclass(frozen=True)
class DoctorSeed:
    name: str
    email: str
    specialty: str
    qualifications: str
    experience_years: int
    rating: float
    consultation_fee: float
    hospital_name: str
    clinic_address: str
    professional_summary: str
    profile_image_url: str


def _doc(
    first: str,
    last: str,
    specialty: str,
    qual: str,
    exp: int,
    rating: float,
    fee: float,
    hospital: str,
    address: str,
    summary: str,
    *,
    email: str | None = None,
) -> DoctorSeed:
    name = f"Dr. {first} {last}"
    slug = email or f"dr.{first.lower()}.{last.lower()}.{specialty.lower().replace(' ', '')}@mediai.clinic"
    return DoctorSeed(
        name=name,
        email=slug,
        specialty=specialty,
        qualifications=qual,
        experience_years=exp,
        rating=rating,
        consultation_fee=fee,
        hospital_name=hospital,
        clinic_address=address,
        professional_summary=summary,
        profile_image_url=default_doctor_avatar_url(name),
    )


_MEDIAI_MAIN = "MediAI Multispecialty Hospital"
_ADDR_NOIDA = "Plot 12, Sector 62, Noida, UP 201301"
_ADDR_GURGAON = "DLF Cyber City, Phase 2, Gurugram, HR 122002"
_ADDR_DELHI = "Saket District Centre, New Delhi 110017"
_ADDR_BANGALORE = "MG Road, Bengaluru, KA 560001"
_PARTNER_APOLLO = "Apollo MediAI Partner Centre"
_PARTNER_MAX = "Max Healthcare — MediAI Wing"


def _specialty_block(
    specialty: str,
    rows: list[tuple],
    legacy_emails: list[str] | None = None,
) -> list[DoctorSeed]:
    out: list[DoctorSeed] = []
    for i, row in enumerate(rows):
        first, last, qual, exp, rating, fee, hospital, address, summary = row
        email = legacy_emails[i] if legacy_emails and i < len(legacy_emails) else None
        out.append(_doc(first, last, specialty, qual, exp, rating, fee, hospital, address, summary, email=email))
    return out


SPECIALTIES: list[str] = [
    "General Physician",
    "Cardiologist",
    "Pediatrician",
    "Dermatologist",
    "Neurologist",
    "Orthopedic Surgeon",
    "ENT Specialist",
    "Gynecologist",
    "Gastroenterologist",
    "Psychiatrist",
    "Ophthalmologist",
    "Urologist",
    "Pulmonologist",
    "Endocrinologist",
    "Oncologist",
]

DOCTOR_CATALOG: list[DoctorSeed] = []

DOCTOR_CATALOG += _specialty_block(
    "General Physician",
    [
        ("Rajesh", "Sharma", "MBBS, MD (General Medicine)", 15, 4.8, 650, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Trusted family physician specializing in diabetes, hypertension, and preventive care for all ages."),
        ("Anita", "Verma", "MBBS, DNB (Family Medicine)", 12, 4.7, 600, _PARTNER_APOLLO, _ADDR_DELHI,
         "Focuses on holistic primary care, annual health check-ups, and lifestyle counselling."),
        ("Vikram", "Iyer", "MBBS, MD, Fellowship in Internal Medicine", 18, 4.9, 750, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Experienced internist known for accurate diagnosis of complex multi-system complaints."),
        ("Priya", "Nair", "MBBS, MD (General Medicine)", 9, 4.6, 550, _PARTNER_MAX, _ADDR_BANGALORE,
         "Compassionate GP with expertise in women's health and geriatric primary care."),
        ("Arjun", "Mehta", "MBBS, MD, Dip. Diabetes", 11, 4.7, 700, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Dedicated to chronic disease management including diabetes, thyroid, and lipid disorders."),
    ],
    legacy_emails=["dr.sharma@clinic.com"],
)

DOCTOR_CATALOG += _specialty_block(
    "Cardiologist",
    [
        ("Suresh", "Patel", "MBBS, MD, DM (Cardiology)", 12, 4.7, 1200, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Interventional cardiologist skilled in angioplasty, heart failure, and preventive cardiac care."),
        ("Meera", "Kapoor", "MBBS, MD, DM (Cardiology)", 16, 4.9, 1400, _PARTNER_APOLLO, _ADDR_DELHI,
         "Expert in echocardiography, arrhythmia management, and post-MI rehabilitation."),
        ("Rahul", "Desai", "MBBS, MD, DM, FSCAI", 14, 4.8, 1300, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Specializes in coronary artery disease, hypertension, and cardiac risk assessment."),
        ("Kavita", "Rao", "MBBS, MD, DM (Cardiology)", 10, 4.6, 1100, _PARTNER_MAX, _ADDR_BANGALORE,
         "Women's heart health specialist with focus on pregnancy-related cardiac conditions."),
        ("Nikhil", "Bansal", "MBBS, MD, DM (Cardiology)", 8, 4.5, 1000, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Young cardiologist passionate about lipid disorders and non-invasive cardiac imaging."),
    ],
    legacy_emails=["dr.patel@clinic.com"],
)

DOCTOR_CATALOG += _specialty_block(
    "Pediatrician",
    [
        ("Lakshmi", "Reddy", "MBBS, MD (Pediatrics)", 20, 4.9, 800, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Beloved pediatrician with two decades of experience in newborn and adolescent care."),
        ("Sanjay", "Malhotra", "MBBS, MD, DCH", 14, 4.8, 750, _PARTNER_APOLLO, _ADDR_DELHI,
         "Expert in childhood infections, vaccination schedules, and growth monitoring."),
        ("Deepa", "Chatterjee", "MBBS, MD (Pediatrics), Neonatology Fellowship", 11, 4.7, 900, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Neonatal and NICU specialist focused on premature infant development."),
        ("Rohit", "Khanna", "MBBS, MD (Pediatrics)", 7, 4.5, 650, _PARTNER_MAX, _ADDR_BANGALORE,
         "Friendly pediatrician known for managing asthma and allergies in children."),
        ("Anjali", "Saxena", "MBBS, MD, Fellowship Pediatric Nutrition", 9, 4.6, 700, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Special interest in childhood obesity, nutrition, and developmental milestones."),
    ],
    legacy_emails=["dr.reddy@clinic.com"],
)

DOCTOR_CATALOG += _specialty_block(
    "Dermatologist",
    [
        ("Harpreet", "Singh", "MBBS, MD (Dermatology)", 8, 4.5, 900, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Treats acne, eczema, psoriasis, and performs cosmetic dermatology procedures."),
        ("Neha", "Agarwal", "MBBS, MD, DDV", 12, 4.8, 1000, _PARTNER_APOLLO, _ADDR_DELHI,
         "Skin cancer screening specialist with expertise in mole mapping and biopsies."),
        ("Karan", "Joshi", "MBBS, MD (Dermatology), Hair Transplant Fellowship", 10, 4.7, 1100, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Leading expert in hair loss, alopecia, and advanced laser skin treatments."),
        ("Pooja", "Menon", "MBBS, MD (Dermatology)", 6, 4.4, 850, _PARTNER_MAX, _ADDR_BANGALORE,
         "Pediatric dermatology focus — rashes, birthmarks, and sensitive skin conditions."),
        ("Amit", "Bhattacharya", "MBBS, MD, Venereology", 15, 4.9, 950, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Comprehensive care for skin infections, STD screening, and chronic dermatitis."),
    ],
    legacy_emails=["dr.singh@clinic.com"],
)

DOCTOR_CATALOG += _specialty_block(
    "Neurologist",
    [
        ("Ravi", "Kumar", "MBBS, MD, DM (Neurology)", 10, 4.6, 1300, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Manages epilepsy, stroke recovery, and chronic headache disorders."),
        ("Shalini", "Pillai", "MBBS, MD, DM (Neurology)", 14, 4.8, 1500, _PARTNER_APOLLO, _ADDR_DELHI,
         "Movement disorder specialist with expertise in Parkinson's and tremor care."),
        ("Gaurav", "Sethi", "MBBS, MD, DM, Epilepsy Fellowship", 9, 4.7, 1250, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Dedicated epilepsy centre lead with EEG and seizure management experience."),
        ("Divya", "Krishnan", "MBBS, MD, DM (Neurology)", 7, 4.5, 1150, _PARTNER_MAX, _ADDR_BANGALORE,
         "Focus on migraine, neuropathy, and multiple sclerosis patient support."),
        ("Manish", "Tiwari", "MBBS, MD, DM (Neurology)", 18, 4.9, 1600, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Senior neurologist renowned for stroke thrombolysis and neuro-rehabilitation."),
    ],
    legacy_emails=["dr.kumar@clinic.com"],
)

DOCTOR_CATALOG += _specialty_block(
    "Orthopedic Surgeon",
    [
        ("Ajay", "Chopra", "MBBS, MS (Orthopedics)", 16, 4.8, 1100, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Joint replacement surgeon specializing in knee and hip arthroplasty."),
        ("Ritu", "Bhardwaj", "MBBS, MS, MCh (Orthopedics)", 12, 4.7, 1200, _PARTNER_APOLLO, _ADDR_DELHI,
         "Sports medicine orthopedist treating ACL injuries and shoulder instability."),
        ("Varun", "Sood", "MBBS, MS (Orthopedics), Spine Fellowship", 14, 4.9, 1400, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Spine surgeon expert in disc herniation, scoliosis, and minimally invasive procedures."),
        ("Sneha", "Dutta", "MBBS, MS (Orthopedics)", 8, 4.5, 950, _PARTNER_MAX, _ADDR_BANGALORE,
         "Hand and wrist specialist for fractures, carpal tunnel, and arthritis."),
        ("Harsh", "Gill", "MBBS, MS, Pediatric Orthopedics", 10, 4.6, 1050, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Pediatric bone deformities, clubfoot, and growth plate injury management."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "ENT Specialist",
    [
        ("Pradeep", "Sinha", "MBBS, MS (ENT)", 13, 4.7, 900, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Treats sinusitis, hearing loss, tonsillitis, and voice disorders."),
        ("Nandini", "Kulkarni", "MBBS, MS (ENT), Head & Neck Surgery", 11, 4.8, 1000, _PARTNER_APOLLO, _ADDR_DELHI,
         "Skilled in endoscopic sinus surgery and thyroid nodule evaluation."),
        ("Imran", "Qureshi", "MBBS, MS (ENT)", 9, 4.6, 850, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Allergy and snoring specialist offering sleep apnea screening."),
        ("Lata", "Hegde", "MBBS, MS (ENT)", 17, 4.9, 1100, _PARTNER_MAX, _ADDR_BANGALORE,
         "Cochlear implant programme lead with pediatric ENT expertise."),
        ("Tarun", "Mishra", "MBBS, MS, Rhinology Fellowship", 7, 4.5, 800, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Rhinology focus — nasal polyps, deviated septum, and chronic rhinitis."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Gynecologist",
    [
        ("Sunita", "Rathore", "MBBS, MS (Obstetrics & Gynecology)", 15, 4.8, 1000, _MEDIAI_MAIN, _ADDR_NOIDA,
         "High-risk pregnancy and laparoscopic gynecology surgery specialist."),
        ("Pallavi", "Shah", "MBBS, MS, Fellowship Reproductive Medicine", 12, 4.9, 1200, _PARTNER_APOLLO, _ADDR_DELHI,
         "IVF and fertility expert supporting couples through assisted conception."),
        ("Rekha", "Pandey", "MBBS, MS (OBGYN)", 10, 4.7, 950, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Menstrual disorders, PCOS management, and adolescent gynecology."),
        ("Jyoti", "Fernandes", "MBBS, MS, Maternal-Fetal Medicine", 14, 4.8, 1150, _PARTNER_MAX, _ADDR_BANGALORE,
         "MFM specialist for twins, gestational diabetes, and preterm care."),
        ("Nisha", "Arora", "MBBS, MS (OBGYN)", 8, 4.6, 900, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Compassionate care for menopause, fibroids, and routine antenatal visits."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Gastroenterologist",
    [
        ("Ashok", "Banerjee", "MBBS, MD, DM (Gastroenterology)", 16, 4.9, 1300, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Hepatology and liver disease expert including hepatitis and cirrhosis care."),
        ("Chetan", "Dalal", "MBBS, MD, DM, ERCP Fellowship", 13, 4.8, 1400, _PARTNER_APOLLO, _ADDR_DELHI,
         "Advanced endoscopist for GI bleeding, polyps, and biliary stone removal."),
        ("Swati", "Lal", "MBBS, MD, DM (Gastroenterology)", 9, 4.6, 1150, _MEDIAI_MAIN, _ADDR_GURGAON,
         "IBS, GERD, and inflammatory bowel disease management specialist."),
        ("Mohit", "Sarin", "MBBS, MD, DM (GI)", 11, 4.7, 1250, _PARTNER_MAX, _ADDR_BANGALORE,
         "Pancreatitis, celiac disease, and nutritional GI disorder focus."),
        ("Radhika", "Venkat", "MBBS, MD, DM, Hepatology", 7, 4.5, 1100, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Fatty liver, NAFLD, and metabolic liver disease counselling and treatment."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Psychiatrist",
    [
        ("Aditya", "Roy", "MBBS, MD (Psychiatry)", 12, 4.7, 1000, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Anxiety, depression, and stress-related disorder therapy with medication management."),
        ("Kiran", "Bedi", "MBBS, MD, Fellowship Child Psychiatry", 10, 4.8, 1100, _PARTNER_APOLLO, _ADDR_DELHI,
         "Adolescent mental health, ADHD, and school-related behavioural concerns."),
        ("Sameer", "Ansari", "MBBS, MD (Psychiatry)", 15, 4.9, 1200, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Addiction medicine and dual-diagnosis treatment programme lead."),
        ("Ishita", "Grover", "MBBS, MD, Psychotherapy Certification", 8, 4.6, 950, _PARTNER_MAX, _ADDR_BANGALORE,
         "Integrates CBT and mindfulness for OCD, phobias, and panic attacks."),
        ("Vivek", "Rastogi", "MBBS, MD (Psychiatry)", 6, 4.5, 900, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Sleep disorders, burnout, and workplace mental wellness counselling."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Ophthalmologist",
    [
        ("Arvind", "Kohli", "MBBS, MS (Ophthalmology)", 14, 4.8, 900, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Cataract and refractive surgery specialist with LASIK experience."),
        ("Smita", "Deshmukh", "MBBS, MS, Fellowship Vitreoretinal", 11, 4.7, 1100, _PARTNER_APOLLO, _ADDR_DELHI,
         "Retina specialist for diabetic retinopathy and macular degeneration."),
        ("Yusuf", "Hussain", "MBBS, MS (Ophthalmology)", 9, 4.6, 850, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Glaucoma screening and medical management programme coordinator."),
        ("Leela", "Subramanian", "MBBS, MS, Pediatric Ophthalmology", 13, 4.9, 1000, _PARTNER_MAX, _ADDR_BANGALORE,
         "Squint, lazy eye, and pediatric vision screening expert."),
        ("Rohan", "Bhatia", "MBBS, MS (Ophthalmology)", 7, 4.5, 800, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Dry eye, conjunctivitis, and corneal infection treatment focus."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Urologist",
    [
        ("Sanjeev", "Yadav", "MBBS, MS, MCh (Urology)", 15, 4.8, 1200, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Kidney stone laser treatment and prostate health specialist."),
        ("Farah", "Siddiqui", "MBBS, MS, MCh (Urology)", 10, 4.7, 1150, _PARTNER_APOLLO, _ADDR_DELHI,
         "Female urology — UTIs, incontinence, and pelvic floor disorders."),
        ("Dev", "Nanda", "MBBS, MS, MCh, Andrology Fellowship", 8, 4.6, 1100, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Male infertility and erectile dysfunction evaluation and care."),
        ("Uma", "Rangan", "MBBS, MS, MCh (Urology)", 12, 4.8, 1250, _PARTNER_MAX, _ADDR_BANGALORE,
         "Uro-oncology focus — bladder and renal tumour multidisciplinary care."),
        ("Prakash", "Dubey", "MBBS, MS, MCh (Urology)", 6, 4.5, 1000, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Pediatric urology — hypospadias, undescended testis, and bedwetting."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Pulmonologist",
    [
        ("Anil", "Thakur", "MBBS, MD, DM (Pulmonology)", 14, 4.8, 1100, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Asthma, COPD, and interstitial lung disease management expert."),
        ("Bharti", "Jain", "MBBS, MD, DM, Critical Care", 11, 4.7, 1200, _PARTNER_APOLLO, _ADDR_DELHI,
         "ICU pulmonologist skilled in ventilator care and ARDS treatment."),
        ("Naveen", "Chawla", "MBBS, MD, DM (Pulmonology)", 9, 4.6, 1000, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Tuberculosis, bronchiectasis, and chronic cough evaluation."),
        ("Shweta", "Oberoi", "MBBS, MD, DM, Allergy Immunology", 7, 4.5, 950, _PARTNER_MAX, _ADDR_BANGALORE,
         "Allergic rhinitis, occupational lung disease, and pulmonary rehab."),
        ("Rajiv", "Sundaram", "MBBS, MD, DM (Pulmonology)", 16, 4.9, 1300, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Sleep medicine and home CPAP therapy programme director."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Endocrinologist",
    [
        ("Madhuri", "Kamath", "MBBS, MD, DM (Endocrinology)", 13, 4.8, 1100, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Diabetes technology — insulin pumps, CGMs, and Type 1 diabetes care."),
        ("Siddharth", "Bajaj", "MBBS, MD, DM (Endocrinology)", 10, 4.7, 1050, _PARTNER_APOLLO, _ADDR_DELHI,
         "Thyroid nodules, hyperthyroidism, and adrenal disorder specialist."),
        ("Geeta", "Ramachandran", "MBBS, MD, DM, Reproductive Endocrinology", 8, 4.6, 1150, _MEDIAI_MAIN, _ADDR_GURGAON,
         "PCOS, hormonal infertility, and metabolic syndrome management."),
        ("Kunal", "Ahuja", "MBBS, MD, DM (Endocrinology)", 6, 4.5, 1000, _PARTNER_MAX, _ADDR_BANGALORE,
         "Pediatric endocrinology — growth disorders and childhood diabetes."),
        ("Parul", "Wadhwa", "MBBS, MD, DM (Endocrinology)", 15, 4.9, 1200, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Osteoporosis, calcium disorders, and post-menopausal hormone health."),
    ],
)

DOCTOR_CATALOG += _specialty_block(
    "Oncologist",
    [
        ("Ramesh", "Swamy", "MBBS, MD, DM (Medical Oncology)", 17, 4.9, 1500, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Chemotherapy protocols and personalised cancer treatment planning."),
        ("Alka", "Mukherjee", "MBBS, MD, DM, Breast Oncology", 12, 4.8, 1400, _PARTNER_APOLLO, _ADDR_DELHI,
         "Breast cancer screening, biopsy coordination, and survivorship care."),
        ("Hemant", "Vora", "MBBS, MD, DM (Radiation Oncology)", 14, 4.8, 1450, _MEDIAI_MAIN, _ADDR_GURGAON,
         "Precision radiotherapy for head, neck, and pelvic malignancies."),
        ("Christina", "Thomas", "MBBS, MD, DM (Medical Oncology)", 9, 4.6, 1300, _PARTNER_MAX, _ADDR_BANGALORE,
         "Lymphoma, leukemia, and blood cancer outpatient management."),
        ("Surendra", "Pawar", "MBBS, MD, DM, Palliative Oncology", 11, 4.7, 1250, _MEDIAI_MAIN, _ADDR_NOIDA,
         "Pain control, palliative care, and quality-of-life support for advanced cancer."),
    ],
)

# Backward compatibility for imports expecting old tuple format
DOCTORS = [
    (d.name, d.email, d.specialty, d.experience_years, d.rating) for d in DOCTOR_CATALOG
]
