/**
 * CodeCelix Rules Engine Service
 * 
 * Integrated with FastAPI backend:
 * - GET    /api/rules
 * - POST   /api/rules
 * - PATCH  /api/rules/{id}
 * - DELETE /api/rules/{id}
 */

// RULES ENGINE REMOVED: changes to rules affect the live backend scoring.// RULES ENGINE REMOVED: changes to rules affect the live backend scoring.
import { apiClient } from './client';
// RULES ENGINE REMOVED
import {
  FraudRule, 
  CreateRulePayload, 
  UpdateRulePayload, 
  RuleAction, 
  RuleOperator, 
  RuleSeverity 
} from '../types/rule';

interface BackendRule {
  id: string;
  name: string;
  description?: string;
  rule_type: string;
  conditions?: any;
  action: string;
  score_impact: number;
  severity: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

const OP_TO_BACKEND: Record<RuleOperator, string> = {
  EQUALS: '==',
  NOT_EQUALS: '!=',
  GREATER_THAN: '>',
  LESS_THAN: '<',
  CONTAINS: 'contains',
  IN_LIST: 'in',
  GEO_MISMATCH: '!=',
};

const OP_FROM_BACKEND: Record<string, RuleOperator> = {
  '==': 'EQUALS',
  '!=': 'NOT_EQUALS',
  '>': 'GREATER_THAN',
  '>=': 'GREATER_THAN',
  '<': 'LESS_THAN',
  '<=': 'LESS_THAN',
  'contains': 'CONTAINS',
  'in': 'IN_LIST',
  'not_in': 'NOT_EQUALS',
};

function mapAction(action?: string): RuleAction {
  const a = (action || '').toLowerCase();
  if (a.includes('block')) return 'BLOCK';
  if (a.includes('2fa') || a.includes('auth')) return 'REQUIRE_2FA';
  if (a.includes('alert')) return 'ALERT_ANALYST';
  return 'FLAG_FOR_REVIEW';
}

function mapActionToBackend(action: RuleAction): string {
  if (action === 'BLOCK') return 'block';
  if (action === 'REQUIRE_2FA') return 'flag_review';
  if (action === 'ALLOW') return 'increase_risk';
  return 'flag_review';
}

function formatRule(r: BackendRule): FraudRule {
  const cond = r.conditions || {};
  const field = cond.field || 'amount';
  const opSymbol = cond.op || '>';
  const threshold = cond.value !== undefined ? String(cond.value) : '1000';

  return {
    id: r.id,
    name: r.name,
    description: r.description || 'Configured heuristic fraud detection rule',
    ruleType: r.rule_type || 'TRANSACTION',
    field,
    operator: OP_FROM_BACKEND[opSymbol] || 'GREATER_THAN',
    threshold,
    action: mapAction(r.action),
    scoreImpact: Number(r.score_impact ?? 25),
    severity: (r.severity || 'MEDIUM').toUpperCase() as RuleSeverity,
    isActive: Boolean(r.is_active),
    createdAt: r.created_at || new Date().toISOString(),
    updatedAt: r.updated_at,
    triggerCount: 0,
  };
}

// RULES ENGINE REMOVED
// CodeCelix Rules Engine Service

export const getRules = async (): Promise<never> => {
  throw new Error('Rules engine is disabled in this deployment.');
};

export const createRule = async (payload: never): Promise<never> => {
  throw new Error('Rules engine is disabled in this deployment.');
};

export const updateRule = async (id: string, payload: never): Promise<never> => {
  throw new Error('Rules engine is disabled in this deployment.');
};

export const deleteRule = async (id: string): Promise<never> => {
  throw new Error('Rules engine is disabled in this deployment.');
};
