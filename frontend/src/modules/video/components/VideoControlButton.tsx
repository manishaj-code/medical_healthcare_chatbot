import type { ReactNode } from 'react';

interface VideoControlButtonProps {
  icon: string;
  label: string;
  active?: boolean;
  danger?: boolean;
  wide?: boolean;
  onClick: () => void;
  children?: ReactNode;
}

export const VideoControlButton = ({
  icon,
  label,
  active = true,
  danger = false,
  wide = false,
  onClick,
  children,
}: VideoControlButtonProps) => {
  const className = [
    'video-control-btn',
    active ? 'video-control-btn--on' : 'video-control-btn--off',
    danger ? 'video-control-btn--danger' : '',
    wide ? 'video-control-btn--wide' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      <span className="material-symbols-outlined" aria-hidden>
        {icon}
      </span>
      {children}
    </button>
  );
};
