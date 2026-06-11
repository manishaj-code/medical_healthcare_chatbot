import { useState } from "react";
import { doctorInitials, resolveDoctorProfileImage } from "../utils/doctorAvatar";

interface Props {
  name: string;
  profileImageUrl?: string | null;
  className?: string;
  initialsClassName?: string;
  alt?: string;
}

export default function DoctorAvatar({
  name,
  profileImageUrl,
  className = "",
  initialsClassName = "",
  alt = "",
}: Props) {
  const [failed, setFailed] = useState(false);
  const src = resolveDoctorProfileImage(name, profileImageUrl);

  if (failed) {
    return (
      <div className={initialsClassName || className} aria-hidden="true">
        {doctorInitials(name)}
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
