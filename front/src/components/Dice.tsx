import React from 'react';

export interface DiceProps {
  value: number | null;
  isRolling: boolean;
  rollId?: number | string | null;
  className?: string;
}

const FACE_ROTATIONS: Record<number, { x: number; y: number }> = {
  1: { x: 0, y: 0 },
  2: { x: 0, y: -90 },
  3: { x: -90, y: 0 },
  4: { x: 90, y: 0 },
  5: { x: 0, y: 90 },
  6: { x: 0, y: 180 },
};

const pipPositions: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

const Dice: React.FC<DiceProps> = ({ value, isRolling, rollId, className = '' }) => {
  const target = FACE_ROTATIONS[value && FACE_ROTATIONS[value] ? value : 1];

  const renderPips = (faceValue: number) => (
    <div className="grid h-full w-full grid-cols-3 gap-0.5 p-1 pointer-events-none">
      {Array.from({ length: 9 }).map((_, index) => (
        <div key={index} className="flex items-center justify-center">
          {pipPositions[faceValue].includes(index) && (
            <div className="h-1.5 w-1.5 rounded-full bg-slate-950 shadow-[inset_0_1px_1px_rgba(255,255,255,0.5)]" />
          )}
        </div>
      ))}
    </div>
  );

  return (
    <div className={`relative flex h-10 w-10 items-center justify-center dice-perspective ${className}`}>
      <div className="absolute -bottom-1 h-1.5 w-7 rounded-full bg-black/20 shadow-[0_2px_4px_rgba(0,0,0,0.25)]" />
      <div
        className="dice-cube"
        style={{
          '--dice-target-x': `${target.x}deg`,
          '--dice-target-y': `${target.y}deg`,
          transform: `rotateX(${target.x}deg) rotateY(${target.y}deg)`,
          animation: isRolling ? 'dice-roll 1.3s cubic-bezier(0.15, 0.85, 0.35, 1.2) forwards' : 'none',
          // Promote the cube only while it actually moves.
          willChange: isRolling ? 'transform' : 'auto',
        } as React.CSSProperties}
        data-roll-id={rollId ?? undefined}
      >
        <div className="dice-face dice-face-front">{renderPips(1)}</div>
        <div className="dice-face dice-face-back">{renderPips(6)}</div>
        <div className="dice-face dice-face-right">{renderPips(2)}</div>
        <div className="dice-face dice-face-left">{renderPips(5)}</div>
        <div className="dice-face dice-face-top">{renderPips(3)}</div>
        <div className="dice-face dice-face-bottom">{renderPips(4)}</div>
      </div>
    </div>
  );
};

// The cube only depends on its own props; memoising keeps dice re-renders out
// of unrelated board updates.
export default React.memo(Dice);
