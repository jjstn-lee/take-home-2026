import { useNavigate } from 'react-router-dom'
import ProductCard from '../components/ProductCard'

export default function CatalogPage({ products, loading, error }) {
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-screen'>
        <div className='animate-spin'>
          <div className='h-8 w-8 border-4 border-primary border-t-transparent rounded-full'></div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className='p-4'>
        <h1 className='text-2xl font-bold mb-2'>Error loading products</h1>
        <p className='text-muted-foreground'>{error}</p>
      </div>
    )
  }

  if (products.length === 0 && !loading) {
    return (
      <div className='p-4'>
        <h1 className='text-2xl font-bold'>No products available</h1>
      </div>
    )
  }

  console.log('Catalog: Rendering with', products.length, 'products (cached from App)')

  return (
    <div className='mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8'>
      <h1 className='text-4xl font-bold tracking-tight mb-8'>Product Catalog</h1>

      <div className='grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
        {products.map((product, index) => (
          <div
            key={index}
            onClick={() => navigate(`/product/${index}`, { state: { product } })}
            className='cursor-pointer'
          >
            <ProductCard product={product} />
          </div>
        ))}
      </div>
    </div>
  )
}
