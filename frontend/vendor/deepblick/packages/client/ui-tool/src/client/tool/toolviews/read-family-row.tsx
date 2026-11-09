/** Single-file read row assembly. */
import type { ReactNode } from 'react'
import { IconBrowseOutlineRegular } from '@deepseek-ai/dsh-client-ui-primitives'
import type { ToolCallViewProps } from '../../contract/slots.ts'
import { toolRowModel } from '../models/tool-call-model.ts'
import { ToolRow, type ToolRowProps } from '../components/ToolRow.tsx'

/** Full row props of a read-family toolview: the runtime share plus its locale seat. */
export type ReadFamilyRowProps = ToolCallViewProps & { t: ToolRowProps['t'] }

/** Read-result card and the optional requested starting line. */
export type ReadFamilyCard = Pick<ToolRowProps, 'read' | 'filePathLine'>

/**
 * Compose a read-family row: the shared chrome and model-derived fields, plus the
 * caller's card material.
 * @param props - the toolview runtime share and locale seat.
 * @param card - the card props this row owns.
 * @returns the assembled ToolRow.
 */
export function readFamilyRow(
  { toolName, block, cwd, home, openFile, inspect, useDisclosure, t }: ReadFamilyRowProps,
  card: ReadFamilyCard,
): ReactNode {
  const model = toolRowModel(toolName, block, cwd, home)
  return (
    <ToolRow
      useDisclosure={useDisclosure}
      t={t}
      variant={model.variant}
      toolName={toolName}
      icon={<IconBrowseOutlineRegular size={14} />}
      title={t(model.titleKey)}
      summary={model.summary}
      bodyRaw={null}
      output={model.output}
      errorSummary={model.errorSummary}
      {...card}
      state={model.state}
      filePath={model.filePath}
      onOpenFile={openFile}
      inspect={inspect}
    />
  )
}
