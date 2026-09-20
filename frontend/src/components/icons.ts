import type { IconifyIcon } from '@iconify/vue'
import type { Component, PropType } from 'vue'
/**
 * Iconify 图标适配层：统一把页面现有的语义化图标组件映射到 Iconify 的 Lucide 图标集。
 *
 * 页面继续使用 `Search`、`RefreshCw` 等稳定组件名，避免在业务模板中散落图标编码；
 * 适配层负责把 Lucide 风格的 `size` 属性转换为 Iconify 的宽高，并透传 class、ARIA 等属性。
 * 图标数据从按需导入的 Iconify 图标包读取，运行时不依赖公共图标 API。
 */
import icon_Activity from '@iconify-icons/lucide/activity'
import icon_ArrowUpRight from '@iconify-icons/lucide/arrow-up-right'
import icon_Ban from '@iconify-icons/lucide/ban'
import icon_BookOpen from '@iconify-icons/lucide/book-open'
import icon_Bot from '@iconify-icons/lucide/bot'
import icon_Box from '@iconify-icons/lucide/box'
import icon_Braces from '@iconify-icons/lucide/braces'
import icon_Building2 from '@iconify-icons/lucide/building-2'
import icon_ChevronDown from '@iconify-icons/lucide/chevron-down'
import icon_ChevronRight from '@iconify-icons/lucide/chevron-right'
import icon_CheckCircle2 from '@iconify-icons/lucide/circle-check'
import icon_XCircle from '@iconify-icons/lucide/circle-x'
import icon_Clock3 from '@iconify-icons/lucide/clock-3'
import icon_UploadCloud from '@iconify-icons/lucide/cloud-upload'
import icon_Copy from '@iconify-icons/lucide/copy'
import icon_Cpu from '@iconify-icons/lucide/cpu'
import icon_Database from '@iconify-icons/lucide/database'
import icon_DatabaseZap from '@iconify-icons/lucide/database-zap'
import icon_MoreHorizontal from '@iconify-icons/lucide/ellipsis'
import icon_ExternalLink from '@iconify-icons/lucide/external-link'
import icon_Eye from '@iconify-icons/lucide/eye'
import icon_FileClock from '@iconify-icons/lucide/file-clock'
import icon_FileCog from '@iconify-icons/lucide/file-cog'
import icon_FileText from '@iconify-icons/lucide/file-text'
import icon_Files from '@iconify-icons/lucide/files'
import icon_Filter from '@iconify-icons/lucide/filter'
import icon_GitBranch from '@iconify-icons/lucide/git-branch'
import icon_GitCompareArrows from '@iconify-icons/lucide/git-compare-arrows'
import icon_GitMerge from '@iconify-icons/lucide/git-merge'
import icon_Hash from '@iconify-icons/lucide/hash'
import icon_History from '@iconify-icons/lucide/history'
import icon_KeyRound from '@iconify-icons/lucide/key-round'
import icon_Layers3 from '@iconify-icons/lucide/layers-3'
import icon_LayoutDashboard from '@iconify-icons/lucide/layout-dashboard'
import icon_Library from '@iconify-icons/lucide/library'
import icon_ListChecks from '@iconify-icons/lucide/list-checks'
import icon_ListTodo from '@iconify-icons/lucide/list-todo'
import icon_LogOut from '@iconify-icons/lucide/log-out'
import icon_MapPin from '@iconify-icons/lucide/map-pin'
import icon_Menu from '@iconify-icons/lucide/menu'
import icon_MessageSquare from '@iconify-icons/lucide/message-square'
import icon_PackageCheck from '@iconify-icons/lucide/package-check'
import icon_PanelLeftClose from '@iconify-icons/lucide/panel-left-close'
import icon_PanelLeftOpen from '@iconify-icons/lucide/panel-left-open'
import icon_Pencil from '@iconify-icons/lucide/pencil'
import icon_Play from '@iconify-icons/lucide/play'
import icon_Plus from '@iconify-icons/lucide/plus'
import icon_Power from '@iconify-icons/lucide/power'
import icon_Radio from '@iconify-icons/lucide/radio'
import icon_RefreshCw from '@iconify-icons/lucide/refresh-cw'
import icon_Rocket from '@iconify-icons/lucide/rocket'
import icon_RotateCcw from '@iconify-icons/lucide/rotate-ccw'
import icon_ScrollText from '@iconify-icons/lucide/scroll-text'
import icon_Search from '@iconify-icons/lucide/search'
import icon_SearchCheck from '@iconify-icons/lucide/search-check'
import icon_SearchX from '@iconify-icons/lucide/search-x'
import icon_Send from '@iconify-icons/lucide/send'
import icon_Settings2 from '@iconify-icons/lucide/settings-2'
import icon_ShieldCheck from '@iconify-icons/lucide/shield-check'
import icon_SlidersHorizontal from '@iconify-icons/lucide/sliders-horizontal'
import icon_Square from '@iconify-icons/lucide/square'
import icon_ThumbsDown from '@iconify-icons/lucide/thumbs-down'
import icon_ThumbsUp from '@iconify-icons/lucide/thumbs-up'
import icon_AlertTriangle from '@iconify-icons/lucide/triangle-alert'
import icon_UserRound from '@iconify-icons/lucide/user-round'
import icon_UserRoundCheck from '@iconify-icons/lucide/user-round-check'
import icon_UserRoundX from '@iconify-icons/lucide/user-round-x'

import icon_Users from '@iconify-icons/lucide/users'
import icon_X from '@iconify-icons/lucide/x'
import { Icon } from '@iconify/vue'
import { defineComponent, h } from 'vue'

type IconSize = string | number

/**
 * 创建带有 Lucide 兼容 size 属性的 Iconify Vue 组件。
 *
 * 组件只接收 Iconify 的图标数据，避免运行时通过名称查询远程图标，
 * 并确保每个图标可以被 Vite 按需打包。
 */
function createIcon(iconData: IconifyIcon): Component {
  return defineComponent({
    inheritAttrs: false,
    props: {
      size: { type: [String, Number] as PropType<IconSize>, default: 24 },
    },
    setup(props, { attrs }) {
      return () =>
        h(Icon, {
          ...attrs,
          icon: iconData,
          width: props.size,
          height: props.size,
        })
    },
  })
}
export const Activity = createIcon(icon_Activity)
export const AlertTriangle = createIcon(icon_AlertTriangle)
export const ArrowUpRight = createIcon(icon_ArrowUpRight)
export const Ban = createIcon(icon_Ban)
export const BookOpen = createIcon(icon_BookOpen)
export const Bot = createIcon(icon_Bot)
export const Box = createIcon(icon_Box)
export const Braces = createIcon(icon_Braces)
export const Building2 = createIcon(icon_Building2)
export const CheckCircle2 = createIcon(icon_CheckCircle2)
export const ChevronDown = createIcon(icon_ChevronDown)
export const ChevronRight = createIcon(icon_ChevronRight)
export const Clock3 = createIcon(icon_Clock3)
export const Copy = createIcon(icon_Copy)
export const Cpu = createIcon(icon_Cpu)
export const Database = createIcon(icon_Database)
export const DatabaseZap = createIcon(icon_DatabaseZap)
export const ExternalLink = createIcon(icon_ExternalLink)
export const Eye = createIcon(icon_Eye)
export const FileClock = createIcon(icon_FileClock)
export const FileCog = createIcon(icon_FileCog)
export const FileText = createIcon(icon_FileText)
export const Files = createIcon(icon_Files)
export const Filter = createIcon(icon_Filter)
export const GitBranch = createIcon(icon_GitBranch)
export const GitCompareArrows = createIcon(icon_GitCompareArrows)
export const GitMerge = createIcon(icon_GitMerge)
export const Hash = createIcon(icon_Hash)
export const History = createIcon(icon_History)
export const KeyRound = createIcon(icon_KeyRound)
export const Layers3 = createIcon(icon_Layers3)
export const Library = createIcon(icon_Library)
export const ListChecks = createIcon(icon_ListChecks)
export const ListTodo = createIcon(icon_ListTodo)
export const LayoutDashboard = createIcon(icon_LayoutDashboard)
export const LogOut = createIcon(icon_LogOut)
export const MapPin = createIcon(icon_MapPin)
export const Menu = createIcon(icon_Menu)
export const MessageSquare = createIcon(icon_MessageSquare)
export const MoreHorizontal = createIcon(icon_MoreHorizontal)
export const PackageCheck = createIcon(icon_PackageCheck)
export const PanelLeftClose = createIcon(icon_PanelLeftClose)
export const PanelLeftOpen = createIcon(icon_PanelLeftOpen)
export const Pencil = createIcon(icon_Pencil)
export const Play = createIcon(icon_Play)
export const Plus = createIcon(icon_Plus)
export const Power = createIcon(icon_Power)
export const Radio = createIcon(icon_Radio)
export const RefreshCw = createIcon(icon_RefreshCw)
export const Rocket = createIcon(icon_Rocket)
export const RotateCcw = createIcon(icon_RotateCcw)
export const Search = createIcon(icon_Search)
export const SearchCheck = createIcon(icon_SearchCheck)
export const SearchX = createIcon(icon_SearchX)
export const Send = createIcon(icon_Send)
export const Settings2 = createIcon(icon_Settings2)
export const ShieldCheck = createIcon(icon_ShieldCheck)
export const ScrollText = createIcon(icon_ScrollText)
export const SlidersHorizontal = createIcon(icon_SlidersHorizontal)
export const Square = createIcon(icon_Square)
export const ThumbsDown = createIcon(icon_ThumbsDown)
export const ThumbsUp = createIcon(icon_ThumbsUp)
export const TriangleAlert = createIcon(icon_AlertTriangle)
export const UploadCloud = createIcon(icon_UploadCloud)
export const UserRound = createIcon(icon_UserRound)
export const UserRoundCheck = createIcon(icon_UserRoundCheck)
export const UserRoundX = createIcon(icon_UserRoundX)
export const Users = createIcon(icon_Users)
export const X = createIcon(icon_X)
export const XCircle = createIcon(icon_XCircle)
