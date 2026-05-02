import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function PDPPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const product = location.state?.product
  const [selectedImageIdx, setSelectedImageIdx] = useState(0)

  console.log('PDPPage: location.state =', location.state)
  console.log('PDPPage: product =', product)

  if (!product) {
    console.error('PDPPage: No product found in state!')
    return (
      <div className='p-4'>
        <h1 className='text-2xl font-bold mb-4'>Product not found</h1>
        <Button onClick={() => navigate('/')}>Back to Catalog</Button>
      </div>
    )
  }

  const images = product.image_urls || []
  const imageUrl = images[selectedImageIdx] || 'https://via.placeholder.com/600x900?text=No+Image'
  const price = product.price?.price || 0
  const originalPrice = product.price?.original_price
  const currency = product.price?.currency || 'USD'
  const isOnSale = originalPrice && originalPrice > price
  const savingsPercentage = isOnSale ? Math.round((1 - price / originalPrice) * 100) : 0
  const offers = product.offers || []

  const handlePrevImage = () => {
    setSelectedImageIdx((prev) => (prev === 0 ? images.length - 1 : prev - 1))
  }

  const handleNextImage = () => {
    setSelectedImageIdx((prev) => (prev === images.length - 1 ? 0 : prev + 1))
  }

  return (
    <div className='mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6'>
      {/* Back Button */}
      <div className='mb-6'>
        <Button variant='outline' onClick={() => navigate(-1)}>
          ← Back
        </Button>
      </div>

      {/* Product Details Grid */}
      <div className='grid grid-cols-1 gap-8 xl:gap-12 lg:grid-cols-[1fr_1.618fr_0.618fr]'>
        {/* Left: Product Info */}
        <div className='flex flex-col gap-6 lg:gap-8'>
          <div className='flex flex-col gap-2 lg:gap-4'>
            <span className='text-sm font-semibold tracking-wide uppercase'>{product.brand} —</span>
            <h2 className='text-xl font-bold tracking-tight text-pretty lg:text-3xl'>{product.name}</h2>
            <p className='text-muted-foreground'>{product.description}</p>
            <div className='flex flex-col gap-1'>
              <div className='flex items-center gap-3'>
                <p className='text-2xl font-bold tracking-tight'>
                  {currency} {price.toFixed(2)}
                </p>
                {isOnSale && (
                  <>
                    <p className='text-lg text-muted-foreground line-through opacity-60'>
                      {currency} {originalPrice.toFixed(2)}
                    </p>
                    <span className='inline-block bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-bold'>
                      Save {savingsPercentage}%
                    </span>
                  </>
                )}
              </div>
            </div>
            <p className='text-sm text-muted-foreground'>{product.category?.name || 'Uncategorized'}</p>
          </div>

        </div>

        {/* Center: Main Image + Thumbnails */}
        <div className='lg:col-start-2'>
          {/* Main Image */}
          <div className='w-full rounded-lg overflow-hidden bg-muted'>
            <div className='relative w-full aspect-[3/4]'>
              <img
                src={imageUrl}
                alt={product.name}
                fetchpriority='high'
                className='w-full h-full object-cover'
              />
              {images.length > 1 && (
                <>
                  <button
                    onClick={handlePrevImage}
                    className='absolute left-0 top-0 bottom-0 w-1/5 flex items-center justify-start pl-3 hover:bg-black/30 transition-colors'
                    aria-label='Previous image'
                  >
                    <span className='text-white text-3xl font-bold'>❮</span>
                  </button>
                  <button
                    onClick={handleNextImage}
                    className='absolute right-0 top-0 bottom-0 w-1/5 flex items-center justify-end pr-3 hover:bg-black/30 transition-colors'
                    aria-label='Next image'
                  >
                    <span className='text-white text-3xl font-bold'>❯</span>
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Thumbnails — directly below the main image */}
          {images.length > 1 && (
            <div className='flex flex-wrap gap-4 mt-4'>
              {images.map((url, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedImageIdx(idx)}
                  className={`ring-offset-background size-16 lg:size-20 cursor-pointer overflow-hidden rounded-sm ring-offset-2 transition-all ${
                    selectedImageIdx === idx ? 'ring-foreground ring-2' : 'opacity-60 hover:opacity-100'
                  }`}
                >
                  <img
                    src={url}
                    alt={`${product.name} ${idx + 1}`}
                    loading='lazy'
                    decoding='async'
                    fetchpriority='low'
                    className='size-full object-cover'
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Product Details & Actions */}
        <div className='flex flex-col gap-6 lg:gap-8'>
          {/* Key Features */}
          {product.key_features?.length > 0 && (
            <div className='flex flex-col gap-2'>
              <h3 className='font-bold text-base'>Key Features</h3>
              <ul className='space-y-2'>
                {product.key_features.map((feature, idx) => (
                  <li key={idx} className='text-sm text-muted-foreground'>
                    • {feature}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Options */}
          {Object.keys(product.options || {}).length > 0 && (
            <div className='flex flex-col gap-4'>
              <h3 className='font-bold text-base'>Available Options</h3>
              {Object.entries(product.options).map(([optionKey, values]) => (
                <div key={optionKey} className='flex flex-col gap-2'>
                  <h4 className='font-semibold text-sm'>
                    {optionKey.charAt(0).toUpperCase() + optionKey.slice(1)}
                  </h4>
                  <p className='text-sm text-muted-foreground'>
                    {Array.isArray(values) ? values.join(', ') : String(values)}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Variant Offers */}
          {offers.length > 0 && (
            <div className='flex flex-col gap-4'>
              <h3 className='font-bold text-base'>Available Offers</h3>
              <div className='space-y-3 max-h-96 overflow-y-auto'>
                {offers.map((offer, idx) => (
                  <div key={idx} className='border rounded-md p-3 text-sm'>
                    <div className='flex items-center justify-between gap-2'>
                      <div className='flex-1'>
                        {Object.keys(offer.options).length > 0 && (
                          <p className='font-semibold text-sm'>
                            {Object.entries(offer.options)
                              .map(([k, v]) => `${k}: ${v}`)
                              .join(' • ')}
                          </p>
                        )}
                        <p className='font-bold text-base mt-1'>
                          {offer.currency} {offer.price.toFixed(2)}
                        </p>
                        {offer.original_price && offer.original_price > offer.price && (
                          <p className='text-xs text-muted-foreground line-through'>
                            {offer.currency} {offer.original_price.toFixed(2)}
                          </p>
                        )}
                      </div>
                      {offer.availability && (
                        <span
                          className={`inline-block px-2 py-1 rounded text-xs font-semibold whitespace-nowrap ${
                            offer.availability === 'InStock'
                              ? 'bg-green-100 text-green-700'
                              : offer.availability === 'OutOfStock'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {offer.availability}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
