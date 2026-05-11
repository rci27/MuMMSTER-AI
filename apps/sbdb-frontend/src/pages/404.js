import React from "react"
import { Link } from "gatsby"
import Layout from "../components/Layout"

export default function NotFoundPage() {
  return (
    <Layout title="Page Not Found">
      <p style={{ color: "#6e8faf" }}>
        That page doesn't exist. <Link to="/">Return home →</Link>
      </p>
    </Layout>
  )
}
