import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

# URScript mapping the S-curve to X and Y (Z is constant at 0.0 relative to start)
urscript_xy = """def repetitive_horizontal_s_curve():
  p_start = get_actual_tcp_pose()
  
  while (True):
    # Forward Horizontal S-curve (X moves forward, Y oscillates)
    # p[dx, dy, dz, rx, ry, rz]
    movel(pose_trans(p_start, p[0.02, 0.03, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.04, 0.04, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.06, 0.03, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.08, 0.00, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.10, -0.03, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.12, -0.04, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.14, -0.03, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.16, 0.00, 0.0, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    
    # Return to start smoothly
    movel(p_start, a=0.2, v=0.1, r=0.0)
    
    sync() # Ensure synchronization
  end
end
"""

def main():
    rclpy.init()
    node = rclpy.create_node('horizontal_s_curve')
    pub = node.create_publisher(String, '/urscript_interface/script_command', 10)
    msg = String()
    msg.data = urscript_xy
    
    # Wait for subscribers to connect
    time.sleep(1.0)
    
    pub.publish(msg)
    node.get_logger().info("Published Horizontal Repetitive S-curve URScript")
    
    time.sleep(1.0)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
