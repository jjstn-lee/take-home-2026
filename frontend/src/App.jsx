import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import CatalogPage from './pages/CatalogPage'
import PDPPage from './pages/PDPPage'

export default function App() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Fetch products once at app level to cache them
  useEffect(() => {
    const fetchProducts = async () => {
      try {
        console.log('App: Fetching products from API')
        const response = await fetch('http://localhost:8000/products')
        if (!response.ok) {
          throw new Error('Failed to fetch products')
        }
        const data = await response.json()
        console.log('App: Products cached in memory', data.length, 'products')
        setProducts(data)
      } catch (err) {
        console.error('App: Error fetching products:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchProducts()
  }, []) // Run only once on app mount

  return (
    <Routes>
      <Route path="/" element={<CatalogPage products={products} loading={loading} error={error} />} />
      <Route path="/product/:id" element={<PDPPage />} />
    </Routes>
  )
}
