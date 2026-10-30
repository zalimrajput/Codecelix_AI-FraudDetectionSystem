import React from 'react';
import { Badge } from '../ui/Badge';
import { RiskLevel } from '../../types/transaction';

export interface RiskBadgeProps {
  level: RiskLevel;
  score?: number;
  showDot?: boolean;
  size?: 'sm' | 'md';
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({
  level,
  score,
  showDot = true,
  size = 'md',
}) => {
  const labelMap: Record<RiskLevel, string> = {
    LOW: 'LOW RISK',
    MEDIUM: 'MED RISK',
    HIGH: 'HIGH RISK',
  };

  return (
    <Badge variant={level.toLowerCase() as any} size={size} dot={showDot}>
      {score !== undefined ? `${labelMap[level]} (${score})` : labelMap[level]}
    </Badge>
  );
};
