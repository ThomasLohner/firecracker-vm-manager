#!/usr/bin/env python3

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from .config_manager import ConfigManager


class FilesystemManager:
    """Manages rootfs building, image/kernel listing and validation"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager or ConfigManager()
    
    def _run_command(self, cmd, check=True, capture_output=True, text=True):
        """Helper method to run subprocess commands with consistent error handling"""
        try:
            return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
        except subprocess.CalledProcessError as e:
            if capture_output:
                print(f"Command failed: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Unexpected error running command: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
    
    def _validate_file_exists(self, file_path, file_type="file"):
        """Validate that a file exists and return Path object"""
        path = Path(file_path)
        if not path.exists():
            print(f"Error: {file_type} {file_path} does not exist", file=sys.stderr)
            return None
        return path
    
    def resolve_kernel_path(self, kernel_filename):
        """Resolve kernel filename to full path using KERNEL_PATH directory"""
        if not kernel_filename:
            return None
        
        env_config = self.config_manager.get_env_config()
        kernel_path_env = env_config.get('KERNEL_PATH')
        
        if not kernel_path_env:
            print("Error: KERNEL_PATH not set in config file", file=sys.stderr)
            return None
        
        kernel_dir = Path(kernel_path_env)
        
        if not kernel_dir.is_dir():
            print(f"Error: KERNEL_PATH '{kernel_path_env}' is not a valid directory", file=sys.stderr)
            return None
        
        kernel_file = kernel_dir / kernel_filename
        if kernel_file.exists():
            return str(kernel_file)
        else:
            print(f"Error: Kernel file '{kernel_filename}' not found in {kernel_dir}", file=sys.stderr)
            print(f"Use './fcm kernels' to see available kernels")
            return None
    
    def build_rootfs(self, vm_name, image_filename, rootfs_size, force_overwrite=False):
        """Build rootfs by copying image file and resizing it"""
        print(f"Building rootfs for VM: {vm_name}...")
        
        env_config = self.config_manager.get_env_config()
        images_path_env = env_config.get('IMAGES_PATH')
        rootfs_path_env = env_config.get('ROOTFS_PATH')
        
        # Validate IMAGES_PATH
        if not images_path_env:
            print("Error: IMAGES_PATH not set in config file", file=sys.stderr)
            return None
            
        images_dir = Path(images_path_env)
        if not images_dir.is_dir():
            print(f"Error: IMAGES_PATH '{images_path_env}' is not a valid directory", file=sys.stderr)
            return None
        
        # Validate ROOTFS_PATH
        if not rootfs_path_env:
            print("Error: ROOTFS_PATH not set in config file", file=sys.stderr)
            return None
            
        rootfs_dir = Path(rootfs_path_env)
        
        # Create rootfs directory if it doesn't exist
        try:
            rootfs_dir.mkdir(parents=True, exist_ok=True)
            print(f"✓ Rootfs directory ready: {rootfs_dir}")
        except Exception as e:
            print(f"Error creating rootfs directory {rootfs_dir}: {e}", file=sys.stderr)
            return None
        
        # Check if image file exists
        image_file = images_dir / image_filename
        if not image_file.exists():
            print(f"Error: Image file '{image_filename}' not found in {images_dir}", file=sys.stderr)
            print(f"Use './fcm images' to see available images")
            return None
        
        # Define destination rootfs file
        rootfs_file = rootfs_dir / f"{vm_name}.ext4"
        
        # Check if rootfs file already exists
        if rootfs_file.exists():
            if not force_overwrite:
                print(f"Error: Rootfs file already exists: {rootfs_file}", file=sys.stderr)
                print(f"A VM with name '{vm_name}' may already have a rootfs file.", file=sys.stderr)
                print(f"Please choose a different VM name, remove the existing file, or use --force-rootfs to overwrite.", file=sys.stderr)
                return None
            else:
                print(f"Warning: Overwriting existing rootfs file: {rootfs_file}")
                print(f"✓ Force overwrite enabled")
        
        try:
            # Copy image file to rootfs location
            print(f"Copying {image_file} -> {rootfs_file}")
            shutil.copy2(image_file, rootfs_file)
            print(f"✓ Image copied to rootfs location")
            
            # Resize the rootfs file
            print(f"Resizing rootfs to {rootfs_size}")
            self._run_command(["resize2fs", str(rootfs_file), rootfs_size])
            print(f"✓ Rootfs resized to {rootfs_size}")
            
            print(f"✓ Rootfs built successfully: {rootfs_file}")
            return str(rootfs_file)
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error building rootfs: {e}", file=sys.stderr)
            # Clean up partially created file
            if rootfs_file.exists():
                try:
                    rootfs_file.unlink()
                    print(f"✓ Cleaned up partial rootfs file: {rootfs_file}")
                except Exception:
                    pass
            return None
    
    def prepare_filesystem(self, args):
        """Prepare filesystem components for VM creation
        
        Args:
            args: Namespace object with VM configuration parameters
                  Uses: args.kernel, args.image, args.name, args.rootfs_size, args.force_rootfs
        
        Returns:
            tuple: (kernel_path, rootfs_path) on success, (None, None) on failure
        """
        # Resolve kernel path (support both filenames and full paths)
        kernel_path = self.resolve_kernel_path(args.kernel)
        if not kernel_path:
            return None, None  # Error message already printed by resolve_kernel_path
        
        # Build rootfs from image
        rootfs_path = self.build_rootfs(
            vm_name=args.name,
            image_filename=args.image,
            rootfs_size=args.rootfs_size,
            force_overwrite=args.force_rootfs
        )
        if not rootfs_path:
            return None, None  # Error message already printed by build_rootfs
        
        return kernel_path, rootfs_path
    
    def get_available_kernels(self):
        """Get available kernel files from KERNEL_PATH directory
        
        Returns:
            list: List of kernel file dictionaries with filename, size, modified
            None: If error occurred
        """
        env_config = self.config_manager.get_env_config()
        kernel_path_env = env_config.get('KERNEL_PATH')
        
        if not kernel_path_env:
            print("Error: KERNEL_PATH not set in config file", file=sys.stderr)
            return None
        
        kernel_dir = Path(kernel_path_env)
        if not kernel_dir.is_dir():
            print(f"Error: KERNEL_PATH '{kernel_path_env}' is not a valid directory", file=sys.stderr)
            return None
            
        try:
            # Look for common kernel file patterns
            kernel_patterns = ['vmlinux*', 'bzImage*', 'kernel*', 'Image*']
            kernel_files = []
            
            for pattern in kernel_patterns:
                kernel_files.extend(kernel_dir.glob(pattern))
            
            # Remove duplicates and sort
            kernel_files = sorted(set(kernel_files), key=lambda x: x.name)
            
            # Build list of kernel data
            kernel_data = []
            for kernel_file in kernel_files:
                try:
                    stat = kernel_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = stat.st_mtime
                    modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')
                    
                    kernel_data.append({
                        'filename': kernel_file.name,
                        'size': f"{size_mb:>6.1f} MB",
                        'modified': modified_str,
                        'path': str(kernel_file)
                    })
                except Exception:
                    kernel_data.append({
                        'filename': kernel_file.name,
                        'size': 'N/A',
                        'modified': 'N/A',
                        'path': str(kernel_file)
                    })
            
            return kernel_data
            
        except Exception as e:
            print(f"Error accessing kernel directory {kernel_dir}: {e}", file=sys.stderr)
            return None
    
    def get_available_images(self):
        """Get available image files from IMAGES_PATH directory
        
        Returns:
            list: List of image file dictionaries with filename, size, modified
            None: If error occurred
        """
        env_config = self.config_manager.get_env_config()
        images_path_env = env_config.get('IMAGES_PATH')
        
        if not images_path_env:
            print("Error: IMAGES_PATH not set in config file", file=sys.stderr)
            return None
        
        images_dir = Path(images_path_env)
        if not images_dir.is_dir():
            print(f"Error: IMAGES_PATH '{images_path_env}' is not a valid directory", file=sys.stderr)
            return None
            
        try:
            # Look for common image file patterns
            image_patterns = ['*.ext4', '*.ext3', '*.ext2', '*.img', '*.qcow2', '*.raw']
            image_files = []
            
            for pattern in image_patterns:
                image_files.extend(images_dir.glob(pattern))
            
            # Remove duplicates and sort
            image_files = sorted(set(image_files), key=lambda x: x.name)
            
            # Build list of image data
            image_data = []
            for image_file in image_files:
                try:
                    stat = image_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = stat.st_mtime
                    modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')
                    
                    image_data.append({
                        'filename': image_file.name,
                        'size': f"{size_mb:>6.1f} MB",
                        'modified': modified_str,
                        'path': str(image_file)
                    })
                except Exception:
                    image_data.append({
                        'filename': image_file.name,
                        'size': 'N/A',
                        'modified': 'N/A',
                        'path': str(image_file)
                    })
            
            return image_data
            
        except Exception as e:
            print(f"Error accessing images directory {images_dir}: {e}", file=sys.stderr)
            return None
    
    # Keep old methods for backward compatibility
    def list_available_kernels(self):
        """List available kernel files from KERNEL_PATH directory (deprecated - use get_available_kernels)"""
        kernel_data = self.get_available_kernels()
        if kernel_data is None:
            return False
        
        env_config = self.config_manager.get_env_config()
        kernel_path = env_config.get('KERNEL_PATH')
        
        print(f"Available kernels in {kernel_path}:")
        
        if not kernel_data:
            print("No kernel files found")
            print("Looking for files matching: vmlinux*, bzImage*, kernel*, Image*")
            return True
        
        print()
        print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
        print('-' * 55)
        
        for kernel in kernel_data:
            print(f"{kernel['filename']:<30} {kernel['size']:<10} {kernel['modified']}")
        
        print()
        print("Usage: ./fcm create --kernel <filename> ...")
        print(f"Example: ./fcm create --kernel {kernel_data[0]['filename']} ...")
        
        return True
    
    def list_available_images(self):
        """List available image files from IMAGES_PATH directory (deprecated - use get_available_images)"""
        env_config = self.config_manager.get_env_config()
        images_path_env = env_config.get('IMAGES_PATH')
        
        if not images_path_env:
            print("Error: IMAGES_PATH not set in config file", file=sys.stderr)
            return False
        
        images_dir = Path(images_path_env)
        if not images_dir.is_dir():
            print(f"Error: IMAGES_PATH '{images_path_env}' is not a valid directory", file=sys.stderr)
            return False
            
        try:
            # Look for common filesystem image patterns
            image_patterns = ['*.ext4', '*.ext3', '*.ext2', '*.img', '*.qcow2', '*.raw']
            image_files = []
            
            for pattern in image_patterns:
                image_files.extend(images_dir.glob(pattern))
            
            # Remove duplicates and sort
            image_files = sorted(set(image_files), key=lambda x: x.name)
            
            if not image_files:
                print(f"No image files found in {images_dir}")
                print("Looking for files matching: *.ext4, *.ext3, *.ext2, *.img, *.qcow2, *.raw")
                return True
            
            print(f"Available images in {images_dir}:")
            print()
            
            # Print table header
            print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
            print('-' * 55)
            
            for image_file in image_files:
                try:
                    stat = image_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = Path(image_file).stat().st_mtime
                    modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')
                    
                    print(f"{image_file.name:<30} {size_mb:>6.1f} MB {modified_str}")
                except Exception as e:
                    print(f"{image_file.name:<30} {'N/A':<10} {'N/A'}")
            
            print()
            print(f"Usage: ./fcm create --image <filename> ...")
            print(f"Example: ./fcm create --image {image_files[0].name} ...")
            
            return True
            
        except Exception as e:
            print(f"Error accessing images directory {images_dir}: {e}", file=sys.stderr)
            return False