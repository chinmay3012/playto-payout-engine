export const paiseToInr = (paise) => (Number(paise || 0) / 100).toFixed(2)

export const inrToPaise = (inr) => {
  const parsed = Number.parseFloat(inr)
  if (Number.isNaN(parsed) || parsed <= 0) return 0
  return Math.round(parsed * 100)
}
