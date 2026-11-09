/** Locally bundled Lucide artwork for the opt-in Deepblick product icon set. */
import type { Context } from '@deepseek-ai/cordis'
import fileSearch from '../assets/lucide-file-search.svg'
import filterList from '../assets/lucide-list-filter.svg'
import panelTop from '../assets/lucide-panel-top.svg'
import panelBottom from '../assets/lucide-panel-bottom.svg'
import panelRight from '../assets/lucide-panel-right.svg'
import terminal from '../assets/lucide-terminal.svg'
import browser from '../assets/lucide-app-window.svg'
import image from '../assets/lucide-image.svg'
import file from '../assets/lucide-file-text.svg'
import newFile from '../assets/lucide-file-plus-2.svg'
import editFile from '../assets/lucide-file-pen-line.svg'
import { EYE_PATH } from './Brand.tsx'
import icon0 from '../assets/lucide-message-square-plus.svg'
import icon1 from '../assets/lucide-search.svg'
import icon2 from '../assets/lucide-globe.svg'
import icon3 from '../assets/lucide-settings.svg'
import icon4 from '../assets/lucide-panel-left.svg'
import icon5 from '../assets/lucide-ellipsis.svg'
import icon6 from '../assets/lucide-plus.svg'
import icon7 from '../assets/lucide-check.svg'
import icon8 from '../assets/lucide-git-branch.svg'
import icon9 from '../assets/lucide-chevron-down.svg'
import icon10 from '../assets/lucide-chevron-left.svg'
import icon11 from '../assets/lucide-chevron-right.svg'
import icon12 from '../assets/lucide-chevron-up.svg'
import icon13 from '../assets/lucide-x.svg'
import icon14 from '../assets/lucide-circle-x.svg'
import icon15 from '../assets/lucide-copy.svg'
import icon16 from '../assets/lucide-refresh-cw.svg'
import icon17 from '../assets/lucide-thumbs-up.svg'
import icon18 from '../assets/lucide-thumbs-down.svg'
import icon19 from '../assets/lucide-share-2.svg'
import icon20 from '../assets/lucide-pencil.svg'
import icon22 from '../assets/lucide-bot.svg'
import icon23 from '../assets/lucide-folder-search.svg'
import icon24 from '../assets/lucide-text-cursor-input.svg'
import icon25 from '../assets/lucide-link.svg'
import icon26 from '../assets/lucide-arrow-up-right.svg'
import icon27 from '../assets/lucide-wand-sparkles.svg'
import icon28 from '../assets/lucide-trash-2.svg'
import icon29 from '../assets/lucide-circle-alert.svg'
import icon30 from '../assets/lucide-circle-check.svg'
import icon31 from '../assets/lucide-triangle-alert.svg'
import icon32 from '../assets/lucide-user.svg'
import icon33 from '../assets/lucide-users.svg'
import icon34 from '../assets/lucide-send.svg'
import icon35 from '../assets/lucide-square.svg'
import icon36 from '../assets/lucide-paperclip.svg'
import icon37 from '../assets/lucide-loader-circle.svg'
import icon38 from '../assets/lucide-download.svg'
import icon39 from '../assets/lucide-play.svg'
import icon40 from '../assets/lucide-pause.svg'
import icon41 from '../assets/lucide-maximize.svg'
import icon42 from '../assets/lucide-code.svg'
import icon43 from '../assets/lucide-puzzle.svg'
import icon44 from '../assets/lucide-plug.svg'
import icon45 from '../assets/lucide-sliders-horizontal.svg'
import icon46 from '../assets/lucide-folder-plus.svg'
import icon47 from '../assets/lucide-folder-open.svg'
import icon48 from '../assets/lucide-folder.svg'
import icon49 from '../assets/lucide-corner-down-right.svg'
import icon50 from '../assets/lucide-sun.svg'
import icon51 from '../assets/lucide-moon.svg'
import icon52 from '../assets/lucide-monitor.svg'
import icon53 from '../assets/lucide-chart-no-axes-combined.svg'
import icon54 from '../assets/lucide-database.svg'
import icon55 from '../assets/lucide-clock-3.svg'
import icon56 from '../assets/lucide-gauge.svg'
import icon57 from '../assets/lucide-arrow-up.svg'
import icon58 from '../assets/lucide-list-ordered.svg'
import icon59 from '../assets/lucide-list-checks.svg'
import icon61 from '../assets/lucide-target.svg'
import icon62 from '../assets/lucide-sparkles.svg'
import icon63 from '../assets/lucide-scan-search.svg'
import icon64 from '../assets/lucide-book-open.svg'
import icon65 from '../assets/lucide-circle-help.svg'
import icon66 from '../assets/lucide-info.svg'
import icon67 from '../assets/lucide-alarm-clock.svg'
import icon68 from '../assets/lucide-archive.svg'
import icon69 from '../assets/lucide-wrap-text.svg'
import icon70 from '../assets/lucide-move-right.svg'
import icon71 from '../assets/lucide-columns-2.svg'
import icon72 from '../assets/lucide-clipboard-list.svg'
import icon73 from '../assets/lucide-fold-vertical.svg'
import icon74 from '../assets/lucide-shield.svg'
import icon75 from '../assets/lucide-archive-restore.svg'
import icon76 from '../assets/lucide-pin.svg'
import icon77 from '../assets/lucide-list.svg'
import icon78 from '../assets/lucide-folder-tree.svg'
import icon79 from '../assets/lucide-chevrons-up-down.svg'
import icon80 from '../assets/lucide-archive-x.svg'
import icon81 from '../assets/lucide-mic.svg'
import icon82 from '../assets/lucide-message-square-text.svg'

import extra0 from '../assets/lucide-shield-check.svg'
import extra1 from '../assets/lucide-shield-plus.svg'
import extra2 from '../assets/lucide-shield-alert.svg'
import extra3 from '../assets/lucide-shield-off.svg'
import extra4 from '../assets/lucide-calendar-days.svg'
import extra5 from '../assets/lucide-log-out.svg'
import extra6 from '../assets/lucide-bell.svg'
import extra7 from '../assets/lucide-compass.svg'
import extra8 from '../assets/lucide-package.svg'
import extra9 from '../assets/lucide-minimize.svg'
import extra10 from '../assets/lucide-minus.svg'
import extra11 from '../assets/lucide-wrench.svg'
import extra12 from '../assets/lucide-braces.svg'
import extra13 from '../assets/lucide-file.svg'

/** Thinking rows show the Deepblick eye mark instead of a generic brain. */
const thinkingEye = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="250 75 1050 650">'
  + `<path fill-rule="evenodd" d="${EYE_PATH}"/>`
  + '<circle cx="799" cy="400" r="161.5" fill="none" stroke="#000" stroke-width="61"/>'
  + '<circle cx="799" cy="400" r="61"/></svg>',
)

const icons = {
  Dockleft: icon4,
  Dockright: panelRight,
  Docktop: panelTop,
  Dockbottom: panelBottom,
  Dockcenter: icon35,
  ShieldCheck: extra0,
  ShieldWrite: extra1,
  ShieldAlert: extra2,
  ShieldOff: extra3,
  Calendar: extra4,
  Logout: extra5,
  Bell: extra6,
  Compass: extra7,
  Package: extra8,
  Minimize: extra9,
  Minus: extra10,
  Wrench: extra11,
  Braces: extra12,
  File: extra13,
  Terminal: terminal,
  BrowserWindow: browser,
  Image: image,
  Document: file,
  DeliverDoc: file,
  NewChatOutline: icon0,
  SearchOutline: icon1,
  GlobeOutline: icon2,
  SettingsOutline: icon3,
  PanelLeftOutline: icon4,
  EllipsisOutline: icon5,
  PlusOutline: icon6,
  CheckOutline: icon7,
  BranchOutline: icon8,
  ChevronDownOutline: icon9,
  ChevronLeftOutline: icon10,
  ChevronRightOutline: icon11,
  TriangleRightFill: icon11,
  ChevronUpOutline: icon12,
  CloseOutline: icon13,
  CloseFill: icon13,
  CloseCircleFill: icon14,
  CopyOutline: icon15,
  RefreshOutline: icon16,
  LikeOutline: icon17,
  LikeFill: icon17,
  DislikeOutline: icon18,
  DislikeFill: icon18,
  ShareOutline: icon19,
  EditOutline: icon20,
  ThinkOutline: thinkingEye,
  AgentPresetOutline: icon22,
  BrowseOutline: icon23,
  ContextInjectionOutline: icon24,
  LinkOutline: icon25,
  RightUpOutline: icon26,
  EnhanceOutline: icon27,
  TrashOutline: icon28,
  WarningOutline: icon29,
  CheckCircleFill: icon30,
  WarningTriangleOutline: icon31,
  UserOutline: icon32,
  UsersOutline: icon33,
  PaperPlaneOutline: icon34,
  StopFill: icon35,
  PaperclipOutline: icon36,
  LoadingOutline: icon37,
  DownloadOutline: icon38,
  PlayOutline: icon39,
  PauseOutline: icon40,
  FullscreenOutline: icon41,
  CodeOutline: icon42,
  CordisPluginOutline: icon43,
  ApiOutline: icon44,
  PersonalizationOutline: icon45,
  ProjectAddOutline: icon46,
  FolderOpenOutline: icon47,
  FolderOpen: icon47,
  FolderClose: icon48,
  TreeCorner: icon49,
  LightOutline: icon50,
  DarkOutline: icon51,
  FollowsystemOutline: icon52,
  DataOutline: icon53,
  DatabaseOutline: icon54,
  ClockOutline: icon55,
  GaugeOutline: icon56,
  SendOutline: icon57,
  QueueOutline: icon58,
  ChecklistOutline: icon59,
  ListPenOutline: icon72,
  GoalOutline: icon61,
  Sparkle: icon62,
  InspectOutline: icon63,
  SkillOutline: icon64,
  QuestionOutline: icon65,
  InfoOutline: icon66,
  PluginPinwheelOutline: icon43,
  AlarmClockOutline: icon67,
  ArchiveOutline: icon68,
  WrapLinesOutline: icon69,
  NowrapFill: icon70,
  WrapFill: icon69,
  CompareSplitOutline: icon71,
  PlanOutline: icon72,
  CompactOutline: icon73,
  ShieldOutline: icon74,
  CheckCircleOutline: icon30,
  UnarchiveOutline: icon75,
  PinOutline: icon76,
  PinFill: icon76,
  FlatListOutline: icon77,
  WorkspaceTreeOutline: icon78,
  ChevronsUpDownOutline: icon79,
  ArchiveOffOutline: icon80,
  ArchiveCheckOutline: icon68,
  SlidersTwoOutline: icon45,
  MicrophoneOutline: icon81,
  ChatLinesOutline: icon82,
  CodeBrackets: icon42,
}

const toolIcons = [
  ['[data-process-activity="search"] svg[data-ui-icon="SearchOutline"], [data-tool="glob"] svg[data-ui-icon="SearchOutline"], [data-tool="grep"] svg[data-ui-icon="SearchOutline"]', fileSearch],
  ['[data-tool="session_event_search"] svg[data-ui-icon="SearchOutline"]', filterList],
  ['[data-tool^="terminal_"] svg[data-ui-icon="CodeOutline"]', terminal],
  ['[data-tool^="schedule_"] svg[data-ui-icon="ClockOutline"]', extra4],
  ['[data-tool="session_event_read"] svg[data-ui-icon="SearchOutline"]', file],
  ['[data-process-activity="commands"] svg[data-ui-icon="ApiOutline"], [data-variant="bash"] svg[data-ui-icon="ApiOutline"]', terminal],
  ['[data-process-activity="webFetch"] svg[data-ui-icon="BrowseOutline"], [data-tool="web_fetch"] svg[data-ui-icon="BrowseOutline"]', browser],
  ['[data-process-activity="readImage"] svg[data-ui-icon="BrowseOutline"], [data-tool="read_image"] svg[data-ui-icon="BrowseOutline"]', image],
  ['[data-process-activity="read"] svg[data-ui-icon="BrowseOutline"], [data-tool="read"] svg[data-ui-icon="BrowseOutline"]', file],
  ['[data-process-activity="write"] svg[data-ui-icon="EditOutline"], [data-tool="write"] svg[data-ui-icon="EditOutline"]', newFile],
  ['[data-process-activity="edit"] svg[data-ui-icon="EditOutline"], [data-tool="edit"] svg[data-ui-icon="EditOutline"]', editFile],
] as const

/**
 * Apply deployment icon artwork without changing file-type or brand marks.
 * @param ctx - Context owning the reversible stylesheet.
 */
export function installDeepblickIcons(ctx: Context): void {
  ctx.effect(() => {
    const style = document.createElement('style')
    style.dataset.deepblickIcons = ''
    const artwork = (targets: string, source: string): string => {
      const selector = targets.split(', ').map(target => `body[data-deepblick] ${target}`).join(', ')
      const image = source.replaceAll('"', '%22')
      return `${selector} { background: currentColor; mask: url("${image}") center / contain no-repeat; }
        ${targets.split(', ').map(target => `body[data-deepblick] ${target} > *`).join(', ')} { visibility: hidden; }`
    }
    style.textContent = [
      ...Object.entries(icons).map(([name, source]) => artwork(`svg[data-ui-icon="${name}"]`, source)),
      ...toolIcons.map(([selector, source]) => artwork(selector, source)),
    ].join('\n') + `
      body[data-deepblick] [data-tool-error-summary] { display: none; }
      body[data-deepblick] [data-menu-section] { display: none; }
    `
    document.head.appendChild(style)
    return () => { style.remove() }
  })
}
