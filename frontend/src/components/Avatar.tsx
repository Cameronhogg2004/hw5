import type { AgentName } from '../types'

/* Fortnite-inspired squad, drawn entirely in HTML/CSS (no images).
   boss = Jonesy-style default with headset, inventory = Peely the banana,
   accounting = Midas in gold, facilities = a hard-hat Constructor,
   customer_service = the Supply Llama. */
export function Avatar({ agent, active }: { agent: AgentName; active?: boolean }) {
  return (
    <div className={`avatar av-${agent} ${active ? 'is-active' : ''}`} aria-hidden="true">
      {agent === 'boss' && (
        <div className="jonesy">
          <span className="hair" />
          <span className="face"><i className="eye l" /><i className="eye r" /><i className="brow l" /><i className="brow r" /><i className="smirk" /></span>
          <span className="headset" /><span className="mic" />
          <span className="shirt"><i className="collar" /></span>
        </div>
      )}
      {agent === 'inventory' && (
        <div className="peely">
          <span className="stem" />
          <span className="body"><i className="eye l" /><i className="eye r" /><i className="mouth" /></span>
          <span className="peel l" /><span className="peel r" />
        </div>
      )}
      {agent === 'accounting' && (
        <div className="midas">
          <span className="hair" />
          <span className="face"><i className="eye l" /><i className="eye r" /><i className="scar" /><i className="mouth" /></span>
          <span className="suit"><i className="tie" /></span>
        </div>
      )}
      {agent === 'facilities' && (
        <div className="constructor">
          <span className="hat"><i className="brim" /></span>
          <span className="face"><i className="eye l" /><i className="eye r" /><i className="beard" /></span>
          <span className="vest"><i className="stripe" /></span>
        </div>
      )}
      {agent === 'customer_service' && (
        <div className="llama">
          <span className="ear l" /><span className="ear r" />
          <span className="head"><i className="eye l" /><i className="eye r" /><i className="snout" /></span>
          <span className="neck"><i className="band b1" /><i className="band b2" /><i className="band b3" /></span>
        </div>
      )}
    </div>
  )
}

export const AGENT_META: Record<AgentName, { label: string; skin: string; role: string; rarity: string }> = {
  boss: { label: 'Boss', skin: 'Jonesy', role: 'Routes the ticket, closes it out', rarity: 'legendary' },
  inventory: { label: 'Inventory', skin: 'Peely', role: 'Stock, vendors, lead times, restocks', rarity: 'uncommon' },
  accounting: { label: 'Accounting', skin: 'Midas', role: 'Cash, invoices, payments, pricing', rarity: 'epic' },
  facilities: { label: 'Facilities', skin: 'Constructor', role: 'Lease, landlord, rent', rarity: 'rare' },
  customer_service: { label: 'Customer Service', skin: 'Supply Llama', role: 'Reply drafts (never sent)', rarity: 'mythic' },
}
