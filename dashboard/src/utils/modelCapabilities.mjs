/**
 * Capability predicates shared by the provider/model selector and its tests.
 *
 * Catalog-backed providers publish the input modalities each model accepts, and
 * the model's configured `modalities` are derived from that declaration when the
 * model is added to a provider source. A model that declares nothing must never
 * be offered for an uploaded attachment, so an undeclared modality fails closed
 * instead of being assumed to work.
 */

/**
 * List the non-text modalities a set of requirements actually demands.
 *
 * @param {readonly string[]|null|undefined} required Requested modalities.
 * @returns {string[]} Requested modalities excluding text.
 */
export function nonTextModalities(required) {
  return (required || []).filter(
    (modality) => typeof modality === 'string' && modality && modality !== 'text'
  )
}

/**
 * Decide whether a model can serve a set of input modalities.
 *
 * @param {{modalities?: string[]}|null|undefined} provider Configured provider
 *   entry from the dashboard API.
 * @param {{modalities?: {input?: string[]}}|null|undefined} metadata Catalog
 *   metadata for the provider's model, when known.
 * @param {readonly string[]|null|undefined} required Non-text modalities the
 *   current entry point actually sends.
 * @returns {boolean} True when every required modality is declared.
 */
export function supportsRequiredModalities(provider, metadata, required) {
  const needed = nonTextModalities(required)
  if (needed.length === 0) return true

  const declaredInputs = metadata?.modalities?.input || []
  const configuredModalities = provider?.modalities
  const configured = Array.isArray(configuredModalities)
    ? configuredModalities
    : []
  // Prefer the catalog declaration when it names modalities; fall back to what
  // the configured provider entry states it accepts.
  const accepted = declaredInputs.length > 0 ? declaredInputs : configured
  return needed.every((modality) => accepted.includes(modality))
}

/**
 * Filter a configured provider list down to the models an entry point may offer.
 *
 * This is the list the selector binds its options to, so an incompatible model
 * never reaches the picker in the first place; the send-time guard is a second
 * line of defence, not a substitute.
 *
 * @param {Array<object>} providers Configured provider entries.
 * @param {Record<string, object>|null|undefined} metadataById Catalog metadata
 *   keyed by model ID.
 * @param {readonly string[]|null|undefined} required Non-text modalities the
 *   current entry point actually sends.
 * @returns {Array<object>} The compatible subset, in input order.
 */
export function filterCompatibleProviders(providers, metadataById, required) {
  const list = Array.isArray(providers) ? providers : []
  if (nonTextModalities(required).length === 0) return list
  const metadata = metadataById || {}
  return list.filter((provider) =>
    supportsRequiredModalities(
      provider,
      metadata[String(provider?.model || '')] || null,
      required
    )
  )
}
