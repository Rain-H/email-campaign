export interface TotalStats {
  contacts: number;
  sent: number;
  newSent: number;
  followupSent: number;
  delivered: number;
  opened: number;
  clicked: number;
  bounced: number;
  replies: number;
  interested: number;
  conversations: number;
}

export interface WeekRow {
  week: string; // "W30"
  weekNum: number;
  year: number;
  weekStart: string; // "07/24"
  sent: number;
  newSent: number;
  followupSent: number;
  replies: number;
  interested: number;
}

export interface ReplyRow {
  email: string;
  repliedAt: string | null; // ISO string
  interested: boolean;
  name: string;
}

export interface PlatformSentRow {
  platform: string;
  sent: number;
  opened: number;
}

export interface PlatformReplyRow {
  platform: string;
  isInterested: boolean;
  count: number;
}

export interface InterestedContactRow {
  name: string;
  email: string;
  conference: string;
  platform: string;
  repliedAt: string; // "YYYY-MM-DD"
}
