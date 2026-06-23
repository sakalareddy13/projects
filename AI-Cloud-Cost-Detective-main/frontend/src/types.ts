export interface Issue {
  service: string
  resource_name: string
  resource_id: string
  region: string
  account_id?: string
  account_name?: string
  issue_type: 'over-provisioned' | 'unused' | 'misconfigured' | 'non-optimized'
  severity: 'high' | 'medium' | 'low'
  explanation: string
  fix_command: string
  potential_monthly_savings: number
}

export interface AnalysisResult {
  summary: string
  total_resources: number
  issues_found: number
  estimated_monthly_savings: number
  estimated_annual_savings: number
  issues: Issue[]
}

export interface ProgressMessage {
  message: string
  status: 'in_progress' | 'complete' | 'error' | 'keepalive'
  data?: AnalysisResult
}

export type CloudProvider = 'aws' | 'azure' | 'gcp'

export interface HistoryItem {
  id: string
  cloud_provider?: CloudProvider
  regions: string[]
  services: string[]
  accounts?: string[]
  resources_scanned: number
  issues_found: number
  estimated_savings: string | null
  status: 'running' | 'complete' | 'failed'
  error_message?: string | null
  created_at: string
}

export interface User {
  id: number
  email: string
}

export interface AWSAccount {
  account_id: string
  name: string
  email?: string
  role_arn?: string
  profile_name?: string
}

export interface AnalysisDetail extends HistoryItem {
  analysis_result: AnalysisResult | null
}
