import { Link } from 'react-router-dom'

function AdminHomePage() {
  return (
    <main className="mx-auto mt-8 max-w-2xl rounded-xl bg-white p-6 shadow">
      <h1 className="text-xl font-bold">Admin Section</h1>
      <p className="mt-2 text-sm text-slate-600">You have access to administrative controls.</p>
      <Link className="mt-4 inline-block rounded border px-3 py-2 text-sm" to="/">Back to dashboard</Link>
    </main>
  )
}

export default AdminHomePage
