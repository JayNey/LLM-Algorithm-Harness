// Preserve synchronous throws while letting explicitly awaited checks settle.
export function recordCheck(assertions, name, fn) {
  const record = { name, pass: false }
  assertions.push(record)
  const fail = (error) => {
    record.error = String(error)
    throw error
  }
  try {
    const value = fn()
    if (value && typeof value.then === 'function')
      return Promise.resolve(value).then(() => {
        record.pass = true
      }, fail)
    record.pass = true
  } catch (error) {
    return fail(error)
  }
}
