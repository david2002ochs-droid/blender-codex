/** Bind the account-owned observable through the framework's reserved hook compartment. */
import type { InjectFace, PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { ModelSelectAccountInjected, ModelSelectInjected } from './slots.ts'
import { useLayoutEffect } from 'react'
import { ModelSelect } from './ModelSelect.tsx'

/**
 * Render the existing picker with authoritative account rights.
 * @param props - Model directory, framework-bound account rights and locale.
 * @returns The existing effort picker.
 */
export function AccountModelSelect({ useEffortAccess, ...props }:
  ModelSelectInjected & InjectFace<ModelSelectAccountInjected> & { locked: boolean } & PropsLocale<'model'>) {
  const effortAccess = useEffortAccess(value => value)
  useLayoutEffect(() => {
    if (props.fastMode === undefined) return
    if (effortAccess.state === 'ready') props.fastMode.resetConnected()
    else props.fastMode.invalidate()
    return () => { props.fastMode?.invalidate() }
  }, [props.fastMode, effortAccess])
  return <ModelSelect {...props} effortAccess={effortAccess} />
}
