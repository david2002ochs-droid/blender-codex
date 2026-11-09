/** Locale-owned Deepblick branding and AI report copy. */
export const zh = {
  name: 'deepblick',
  tagline: '你的 Excel AI 伙伴。',
  tasks: '自动化任务',
  reportAiContent: '举报 AI 内容',
  reportAiContentSubject: 'deepblick AI 内容举报',
  reportAiContentBody: '请说明哪些 AI 内容不当以及原因。\r\n\r\n仅填写你希望与 deepblick 分享的信息。本邮件草稿不会自动附加聊天记录或工作簿。',
}

/** Deepblick namespace keys. */
export type DeepblickKey = keyof typeof zh

/** English Deepblick copy. */
export const en = {
  name: 'deepblick',
  tagline: 'Your AI partner for Excel.',
  tasks: 'Automation tasks',
  reportAiContent: 'Report AI content',
  reportAiContentSubject: 'deepblick AI content report',
  reportAiContentBody: 'Describe the AI content and why it is inappropriate.\r\n\r\nInclude only information you want to share with deepblick. No chat or workbook is attached automatically.',
} satisfies Record<DeepblickKey, string>
